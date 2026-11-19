import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from vmforge import lab
from vmforge.providers.virtualbox import VirtualBox, VMError
from vmforge.protection import ProtectionConfig
import test_import_disk as import_tests


VM = '10000000-0000-4000-8000-000000000001'
OTHER = '20000000-0000-4000-8000-000000000001'


class SecurityTests(unittest.TestCase):
    def test_purge_revalidates_after_confirmation(self):
        from vmforge.recovery import purge_main
        for changed in ('name', 'VMState', 'CfgFile'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / 'test.vbox'
                config.write_text('fixture', encoding='utf-8')
                info = dict(name='VMForge-Test', VMState='poweroff', CfgFile=str(config))
                current = dict(info, **{changed: 'changed'})
                vb = Mock()
                vb.require_writable.return_value = VM
                vb.status.return_value = 'poweroff'
                vb.info.side_effect = [info, current]
                with patch('vmforge.recovery.VirtualBox', return_value=vb), \
                     patch('vmforge.recovery.load_protection', return_value=ProtectionConfig(frozenset(), frozenset(), frozenset())), \
                     patch('builtins.input', return_value='EXCLUIR ' + VM), \
                     patch('subprocess.run') as process, redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(ValueError, 'mudou'):
                        purge_main(['--uuid', VM, '--vbox', str(config), '--test-root', str(root)])
                    process.assert_not_called()

    def test_wrong_uuid_rejected(self):
        vb = VirtualBox('fake')
        with patch.object(vb, 'info', return_value={'UUID': OTHER, 'name': 'test'}), \
             patch('vmforge.providers.virtualbox.load_protection', return_value=ProtectionConfig(frozenset(), frozenset(), frozenset())):
            with self.assertRaisesRegex(VMError, 'UUID retornado'):
                vb.require_writable(VM)

    def test_journal_does_not_follow_existing_temporary_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            victim = root / 'original'
            victim.write_text('preserve', encoding='utf-8')
            (root / 'lab.tmp').hardlink_to(victim)
            with self.assertRaises(FileExistsError):
                lab.save(root / 'lab.json', {})
            self.assertEqual(victim.read_text(), 'preserve')

    def test_insufficient_space_before_any_backend_write(self):
        case = import_tests.ImportPlanTests('test_valid_dry_plan')
        case.setUp()
        try:
            with patch('vmforge.import_disk.shutil.disk_usage', return_value=Mock(free=0)):
                with self.assertRaisesRegex(ValueError, 'Espaço insuficiente'):
                    case.invoke()
            self.assertFalse((case.root / 'TestTarget').exists())
        finally:
            case.doCleanups()

    def test_interrupt_during_create_preserves_files(self):
        case = import_tests.ImportExecutionTests('test_success_private_clone_and_uuid_targets')
        case.setUp()
        original = case.fake
        def interrupt(binary, *args, **kwargs):
            result = original(binary, *args, **kwargs)
            if args[0] == 'createvm':
                raise KeyboardInterrupt()
            return result
        case.fake = interrupt
        try:
            with self.assertRaisesRegex(VMError, 'Estado parcial preservado'):
                case.run_import()
            case.assert_origin()
            self.assertTrue((case.root / 'TestTarget').is_dir())
        finally:
            case.doCleanups()


