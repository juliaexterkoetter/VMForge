"""Read-only tests for VMDK import planning."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from vmforge.import_disk import plan
from vmforge.cli import main
from vmforge.protection import ProtectionConfig


class ImportPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'trusted.vmdk'
        self.src.write_bytes(b'placeholder')  # planning does not open image content
        self.vb = Mock()
        self.vb.list_vms.return_value = []
        self.vb.binary = 'VBoxManage'
        self.cfg = ProtectionConfig(frozenset(), frozenset(), frozenset({2222}))

    def invoke(self, **overrides):
        args = dict(source=self.src, name='TestTarget', basefolder=self.root,
                    hostonly='VirtualBox Host-Only Ethernet Adapter', vb=self.vb)
        args.update(overrides)
        with patch('vmforge.import_disk.load_protection', return_value=self.cfg), \
             patch('vmforge.import_disk._call', return_value='Name:            VirtualBox Host-Only Ethernet Adapter\n'):
            return plan(**args)

    def test_valid_dry_plan(self):
        p = self.invoke()
        self.assertEqual(p['name'], 'TestTarget')
        self.assertFalse(p['target'].exists())

    def test_existing_target_rejected(self):
        (self.root / 'TestTarget').mkdir()
        with self.assertRaises(ValueError):
            self.invoke()

    def test_windows_reserved_names_rejected_before_virtualbox_queries(self):
        reserved = ['CON', 'PRN', 'AUX', 'NUL']
        reserved += [f'{prefix}{number}' for prefix in ('COM', 'LPT')
                     for number in range(1, 10)]
        for device in reserved:
            for name in (device, device.lower(), device + '.lab'):
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, 'Nome inválido para Windows'):
                        self.invoke(name=name)
                    self.vb.list_vms.assert_not_called()

    def test_trailing_dot_rejected(self):
        for name in ('Lab.', 'Lab..'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'Nome inválido para Windows'):
                    self.invoke(name=name)
                self.vb.list_vms.assert_not_called()

    def test_non_reserved_names_remain_valid(self):
        for name in ('Lab.v1', 'console', 'CON-lab', 'COM10', 'LPT10', 'a' * 64):
            with self.subTest(name=name):
                planned = self.invoke(name=name)
                self.assertEqual(planned['target'], self.root / name)
                self.assertFalse(planned['target'].exists())

    def test_existing_vm_rejected(self):
        self.vb.list_vms.return_value = [{'name': 'testtarget', 'uuid': 'abc'}]
        with self.assertRaises(ValueError):
            self.invoke()

    def test_non_vmdk_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke(source=self.root / 'not-found.vmdk')

    def test_protected_name_rejected(self):
        self.cfg = ProtectionConfig(frozenset(), frozenset({'testtarget'}), frozenset())
        with self.assertRaises(ValueError):
            self.invoke()


class ImportCancellationTests(unittest.TestCase):
    def test_interrupted_confirmation_does_not_execute(self):
        argv = ['import-disk', '--source', 'trusted.vmdk', '--name', 'TestTarget',
                '--basefolder', 'unused', '--hostonly', 'test-interface', '--execute']
        planned = dict(name='TestTarget', source='trusted.vmdk', target='unused/TestTarget',
                       hostonly='test-interface', ram=512, cpus=1)
        for interruption in (EOFError, KeyboardInterrupt):
            with self.subTest(interruption=interruption.__name__):
                output = io.StringIO()
                with patch('vmforge.import_disk.plan', return_value=planned), \
                     patch('builtins.input', side_effect=interruption), \
                     patch('vmforge.import_disk.execute') as execute, \
                     redirect_stdout(output):
                    result = main(argv)
                self.assertEqual(result, 1)
                self.assertIn('Importação interrompida pelo usuário.', output.getvalue())
                self.assertNotIn('VM criada:', output.getvalue())
                execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
