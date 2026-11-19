"""Read-only tests for VMDK import planning."""
import io
import hashlib
import struct
import subprocess
import uuid
import xml.etree.ElementTree as ET
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch

from vmforge.import_disk import plan
from vmforge.cli import main
from vmforge.import_disk import plan, execute, _call
from vmforge.providers.virtualbox import VMError
from vmforge.protection import ProtectionConfig


class ImportPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'trusted.vmdk'
        self.src.write_text('# Disk DescriptorFile\nversion=1\nCID=12345678\nparentCID=ffffffff\ncreateType="monolithicFlat"\nRW 1 FLAT "extent.vmdk" 0\n', encoding='ascii')
        self.extent = self.root / 'extent.vmdk'
        self.extent.write_bytes(bytes(512))
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
                       hostonly='test-interface', ram=512, cpus=1, files={})
        for interruption in (EOFError, KeyboardInterrupt):
            with self.subTest(interruption=interruption.__name__):
                output = io.StringIO()
                with patch('vmforge.import_disk.plan', return_value=planned), \
                     patch('builtins.input', side_effect=interruption), \
                     patch('vmforge.import_disk.execute') as execute, \
                     redirect_stdout(output), redirect_stderr(output):
                    result = main(argv)
                self.assertEqual(result, 1)
                self.assertIn('Importação interrompida pelo usuário.', output.getvalue())
                self.assertNotIn('VM criada:', output.getvalue())
                execute.assert_not_called()
class ImportExecutionTests(ImportPlanTests):
    def setUp(self):
        super().setUp()
        # Defense in depth: any accidental real process launch fails this test.
        blocker = patch('subprocess.run', side_effect=AssertionError('Real subprocess forbidden'))
        blocker.start()
        self.addCleanup(blocker.stop)
        self.calls = []
        self.identity = None
        self.fail = None
        self.bad_clone = False
        self.bad_network = False
        self.protect_after_register = False
        self.mutate_source = False
        self.info = {}
        self.vb.info.side_effect = lambda identity: dict(self.info)
        self.initial = {p: p.read_bytes() for p in (self.src, self.extent)}

    def fake(self, binary, *args, **kwargs):
        self.calls.append(args)
        op = args[0]
        if op == 'list':
            return 'Name: VirtualBox Host-Only Ethernet Adapter\n'
        if op == 'createvm':
            self.assertNotIn('--register', args)
            self.identity = args[args.index('--uuid') + 1]
            target = self.root / 'TestTarget'
            target.mkdir()
            (target / 'TestTarget.vbox').write_text(
                f'<VirtualBox><Machine uuid="{{{self.identity}}}" name="TestTarget">'
                '<Hardware><Network><Adapter slot="0" enabled="true"><NAT/></Adapter>'
                '</Network></Hardware></Machine></VirtualBox>')
            self.info = dict(UUID=self.identity, name='TestTarget', VMState='poweroff')
        if op == self.fail:
            raise VMError('injected failure')
        if op == 'clonemedium':
            self.assertNotEqual(args[2], self.src)
            self.assertEqual(Path(args[2]).read_bytes(), self.initial[self.src])
            # Even a backend that writes its input can only touch the private copy.
            Path(args[2]).write_bytes(b'backend changed private descriptor')
            header = bytearray(512)
            struct.pack_into('<I', header, 64, 0xbeda107f)
            struct.pack_into('<I', header, 68, 0x00010001)
            struct.pack_into('<I', header, 76, 1)
            header[392:408] = uuid.uuid4().bytes_le
            if self.bad_clone:
                header[424] = 1
            Path(args[3]).write_bytes(header)
            if self.mutate_source:
                self.extent.write_bytes(b'x' * 512)
        if op == 'registervm':
            tree = ET.parse(args[1])
            for adapter in tree.iter('Adapter'):
                self.assertEqual(adapter.get('enabled'), 'false')
                self.assertEqual(list(adapter), [])
            if self.protect_after_register:
                self.cfg = ProtectionConfig(frozenset({self.identity}), frozenset(), frozenset())
        if op == 'modifyvm':
            self.assertEqual(args[1], self.identity)
            self.assertNotIn('nat', args)
            self.assertNotIn('bridged', args)
            self.info.update(nic1='nat' if self.bad_network else 'hostonly',
                             hostonlyadapter1='VirtualBox Host-Only Ethernet Adapter')
            self.info.update({f'nic{i}': 'none' for i in range(2, 9)})
        return ''

    def run_import(self, p=None):
        with patch('vmforge.import_disk.VirtualBox', return_value=self.vb), \
             patch('vmforge.import_disk.load_protection', side_effect=lambda: self.cfg), \
             patch('vmforge.import_disk._call', side_effect=self.fake):
            p = p or plan(self.src, 'TestTarget', self.root,
                          'VirtualBox Host-Only Ethernet Adapter', vb=self.vb)
            return execute(p)

    def assert_origin(self):
        for path, data in self.initial.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), hashlib.sha256(data).digest())

    def test_success_private_clone_and_uuid_targets(self):
        self.assertEqual(self.run_import(), 'TestTarget')
        self.assert_origin()
        for args in self.calls:
            if args[0] in ('modifyvm', 'storagectl', 'storageattach'):
                self.assertEqual(args[1], self.identity)
        attached = next(args for args in self.calls if args[0] == 'storageattach')
        self.assertEqual(attached[-1], self.root / 'TestTarget' / 'TestTarget.vdi')
        self.assertFalse(any(args[0] == 'startvm' for args in self.calls))

    def test_each_mutation_failure_stops_and_preserves_source(self):
        for failure in ('createvm', 'clonemedium', 'registervm', 'modifyvm', 'storagectl', 'storageattach'):
            with self.subTest(failure=failure):
                # Each attempt uses a separate project-local fixture.
                case = ImportExecutionTests('test_success_private_clone_and_uuid_targets')
                case.setUp()
                try:
                    case.fail = failure
                    with case.assertRaisesRegex(VMError, failure):
                        case.run_import()
                    case.assert_origin()
                    case.assertEqual(case.calls[-1][0], failure)
                    case.assertFalse(any(c[0] in ('unregistervm', 'closemedium', 'startvm') for c in case.calls))
                finally:
                    case.doCleanups()

    def test_dependent_clone_never_registered(self):
        self.bad_clone = True
        with self.assertRaisesRegex(VMError, 'dependente'):
            self.run_import()
        self.assertFalse(any(c[0] == 'registervm' for c in self.calls))
        self.assert_origin()

    def test_uuid_protection_reloaded_after_registration(self):
        self.protect_after_register = True
        with self.assertRaises(VMError):
            self.run_import()
        self.assertFalse(any(c[0] == 'modifyvm' for c in self.calls))
        self.assert_origin()

    def test_network_readback_fail_closed(self):
        self.bad_network = True
        with self.assertRaisesRegex(VMError, 'Host-only'):
            self.run_import()
        self.assertFalse(any(c[0] == 'storageattach' for c in self.calls))

    def test_change_between_plan_and_execution_blocks_creation(self):
        p = self.invoke()
        self.extent.write_bytes(b'x' * 512)
        with self.assertRaisesRegex(VMError, 'mudou'):
            self.run_import(p)
        self.assertFalse(any(c[0] == 'createvm' for c in self.calls))

    def test_external_source_change_is_reported(self):
        self.mutate_source = True
        with self.assertRaisesRegex(VMError, 'origem imutavel'):
            self.run_import()

    def test_invalid_descriptors_fail_before_backend(self):
        original = self.src.read_text()
        cases = ['placeholder', original.replace('ffffffff', '12345678'),
                 original + 'parentFileNameHint="parent.vmdk"\n',
                 original.replace('extent.vmdk', '../extent.vmdk'),
                 original.replace('extent.vmdk', 'C:\\disk.vmdk'),
                 original.replace('monolithicFlat', 'fullDevice'),
                 original.replace('RW 1', 'RW 2'),
                 original.replace('extent.vmdk', 'missing.vmdk'),
                 original + 'CID=12345678\n']
        for content in cases:
            with self.subTest(content=content):
                self.src.write_text(content)
                with self.assertRaises(ValueError):
                    self.invoke()

    def test_split_extents_and_sparse_descriptors(self):
        second = self.root / 'second.vmdk'
        second.write_bytes(bytes(512))
        self.src.write_text('version=1\nCID=12345678\nparentCID=ffffffff\n'
                            'createType="twoGbMaxExtentFlat"\nRW 1 FLAT "extent.vmdk" 0\n'
                            'RW 1 FLAT "second.vmdk" 0\n')
        self.assertEqual(set(self.invoke()['files']), {self.src, self.extent, second})
        descriptor = ('version=1\nCID=12345678\nparentCID=ffffffff\n'
                      'createType="monolithicSparse"\nRW 1 SPARSE "trusted.vmdk"\n').encode('ascii')
        header = bytearray(512)
        header[:4] = b'KDMV'
        struct.pack_into('<I', header, 4, 1)
        struct.pack_into('<Q', header, 12, 1)
        struct.pack_into('<QQ', header, 28, 1, 1)
        self.src.write_bytes(header + descriptor.ljust(512, b'\0'))
        self.assertEqual(set(self.invoke()['files']), {self.src})
        struct.pack_into('<Q', header, 28, 999)
        self.src.write_bytes(header + descriptor.ljust(512, b'\0'))
        with self.assertRaises(ValueError):
            self.invoke()
        self.src.write_text('version=1\nCID=12345678\nparentCID=ffffffff\n'
                            'createType="twoGbMaxExtentSparse"\nRW 1 SPARSE "extent.vmdk"\n')
        struct.pack_into('<QQ', header, 28, 0, 0)
        self.extent.write_bytes(header)
        self.assertEqual(set(self.invoke()['files']), {self.src, self.extent})

    def test_hardlinked_source_rejected(self):
        link = self.root / 'alias.vmdk'
        link.hardlink_to(self.extent)
        with self.assertRaises(ValueError):
            self.invoke()

    def test_interface_and_limits_fail_closed(self):
        for kwargs in ({'hostonly': 'NAT'}, {'hostonly': 'bad\nname'},
                       {'ram': 255}, {'cpus': 0}, {'name': '../existing'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.invoke(**kwargs)

    def test_generated_uuid_collision_rejected_before_creation(self):
        identity = uuid.uuid4()
        self.vb.list_vms.return_value = [{'name': 'Other', 'uuid': str(identity)}]
        with patch('vmforge.import_disk.uuid.uuid4', return_value=identity):
            with self.assertRaisesRegex(VMError, 'UUID'):
                self.run_import()
        self.assertFalse(any(c[0] == 'createvm' for c in self.calls))

    def test_changed_registered_identity_blocks_mutation(self):
        self.vb.info.side_effect = lambda identity: dict(self.info, UUID=str(uuid.uuid4()))
        with self.assertRaises(VMError):
            self.run_import()
        self.assertFalse(any(c[0] == 'modifyvm' for c in self.calls))

    def test_cli_dry_run_cancel_and_forwarding(self):
        from vmforge.import_disk import main
        from vmforge.cli import main as cli_main
        args = ['--source', str(self.src), '--name', 'TestTarget', '--basefolder',
                str(self.root), '--hostonly', 'VirtualBox Host-Only Ethernet Adapter']
        with patch('vmforge.import_disk.plan', return_value=self.invoke()), \
             patch('vmforge.import_disk.execute') as run, patch('builtins.print'):
            self.assertEqual(main(args), 0)
            with patch('builtins.input', return_value='NAO'):
                self.assertEqual(cli_main(['import-disk', *args, '--execute']), 0)
            with patch('builtins.input', side_effect=EOFError):
                self.assertEqual(main([*args, '--execute']), 1)
            run.assert_not_called()

    def test_uuid_as_name_is_protected(self):
        identity = str(uuid.uuid4())
        self.cfg = ProtectionConfig(frozenset({identity}), frozenset(), frozenset())
        with self.assertRaises(ValueError):
            self.invoke(name=identity)

    def test_missing_protection_fails_closed(self):
        with patch('vmforge.import_disk.load_protection', side_effect=ValueError('missing')):
            with self.assertRaises(ValueError):
                plan(self.src, 'TestTarget', self.root, 'hostonly', vb=self.vb)
        self.assertEqual(self.calls, [])

    def test_call_wraps_timeout_oserror_and_nonzero(self):
        for error in (OSError('fake'), subprocess.TimeoutExpired('fake', 1)):
            with patch('subprocess.run', side_effect=error):
                with self.assertRaises(VMError):
                    _call('fake', 'createvm')
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='failure', stdout='')):
            with self.assertRaisesRegex(VMError, 'failure'):
                _call('fake', 'createvm')


if __name__ == '__main__':
    unittest.main()
