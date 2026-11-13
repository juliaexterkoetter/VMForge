import struct
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch, Mock
from vmforge.appliance import validate_appliance, PROTECTED_UUID
from vmforge.providers.virtualbox import VirtualBox, VMError

MACHINE = '10000000-0000-4000-8000-000000000001'
DISK = '20000000-0000-4000-8000-000000000001'


def fixture(root, identity=MACHINE, location='disk.vdi', extra=''):
    path = root/'kali.vbox'
    path.write_text(f'<VirtualBox><Machine uuid="{{{identity}}}" name="Teste"><MediaRegistry><HardDisks><HardDisk uuid="{{{DISK}}}" location="{location}" format="VDI"/></HardDisks></MediaRegistry><Hardware><StorageControllers><Image uuid="{{{DISK}}}"/></StorageControllers>{extra}</Hardware></Machine></VirtualBox>', encoding='utf-8')
    header = bytearray(512)
    struct.pack_into('<III', header, 64, 0xbeda107f, 0x00010001, 400)
    struct.pack_into('<I', header, 76, 1)
    header[392:408] = uuid.UUID(DISK).bytes_le
    (root/'disk.vdi').write_bytes(header)
    return path


class ApplianceTests(unittest.TestCase):
    def test_valid_pair(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(validate_appliance(fixture(Path(td)))['uuid'], MACHINE)

    def test_protected_uuid(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'protegido'):
                validate_appliance(fixture(Path(td), identity=PROTECTED_UUID))

    def test_external_paths(self):
        with tempfile.TemporaryDirectory() as td:
            for location in ('../disk.vdi', 'C:/disk.vdi', '//server/disk.vdi'):
                with self.subTest(location=location), self.assertRaises(ValueError):
                    validate_appliance(fixture(Path(td), location=location))

    def test_external_resources(self):
        with tempfile.TemporaryDirectory() as td:
            for extra in ('<Snapshot/>', '<SharedFolder hostPath="C:/personal"/>', '<HostDrive/>', '<Image uuid="{30000000-0000-4000-8000-000000000001}"/>'):
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    validate_appliance(fixture(Path(td), extra=extra))

    def test_bad_xml(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'test.vbox'
            for content in ('not XML', '<VirtualBox/>', '<!DOCTYPE a><VirtualBox/>'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    validate_appliance(path)

    def test_missing_and_invalid_vdi(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = fixture(root)
            (root/'disk.vdi').unlink()
            with self.assertRaises(ValueError):
                validate_appliance(path)
            (root/'disk.vdi').write_bytes(b'invalid')
            with self.assertRaises(ValueError):
                validate_appliance(path)

    def test_parent_uuid_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = fixture(root)
            header = bytearray((root/'disk.vdi').read_bytes())
            header[424] = 1
            (root/'disk.vdi').write_bytes(header)
            with self.assertRaises(ValueError):
                validate_appliance(path)


class ProtectedOperationTests(unittest.TestCase):
    def setUp(self):
        self.vbox = VirtualBox(binary='fake')

    def test_direct_uuid_all_mutations_blocked(self):
        for command in ('modifyvm', 'startvm', 'controlvm', 'snapshot', 'guestcontrol'):
            with self.subTest(command=command), patch('vmforge.providers.virtualbox.subprocess.run') as process:
                with self.assertRaises(VMError):
                    self.vbox.run(command, PROTECTED_UUID)
                process.assert_not_called()

    def test_renamed_protected_vm_blocked_by_uuid(self):
        with patch.object(self.vbox, 'info', return_value={'UUID': PROTECTED_UUID}), patch('vmforge.providers.virtualbox.subprocess.run') as process:
            with self.assertRaises(VMError):
                self.vbox.run('startvm', 'renamed')
            process.assert_not_called()

    def test_unknown_uuid_fails_closed(self):
        with patch.object(self.vbox, 'info', return_value={}), patch('vmforge.providers.virtualbox.subprocess.run') as process:
            with self.assertRaises(VMError):
                self.vbox.run('startvm', 'unknown')
            process.assert_not_called()

    def test_mutation_uses_resolved_uuid(self):
        with patch.object(self.vbox, 'info', return_value={'UUID': MACHINE}), patch('vmforge.providers.virtualbox.subprocess.run', return_value=Mock(returncode=0, stdout='ok')) as process:
            self.vbox.run('startvm', 'new')
            self.assertEqual(process.call_args.args[0][2], MACHINE)

    def test_unsupported_destructive_command_blocked(self):
        with patch('vmforge.providers.virtualbox.subprocess.run') as process:
            with self.assertRaises(VMError):
                self.vbox.run('unregistervm', MACHINE, '--delete')
            process.assert_not_called()

    def test_nat_conflict_before_mutation(self):
        with patch.object(self.vbox, 'status', return_value='poweroff'), patch.object(self.vbox, 'info', return_value={'Forwarding(0)': 'existing'}), patch.object(self.vbox, 'run') as run:
            with self.assertRaises(VMError):
                self.vbox.configure('new', 4096, 2, 2223)
            run.assert_not_called()

    def test_protected_registration_blocked(self):
        with tempfile.TemporaryDirectory() as td, patch('vmforge.providers.virtualbox.subprocess.run') as process:
            with self.assertRaises(VMError):
                self.vbox.register(fixture(Path(td), identity=PROTECTED_UUID))
            process.assert_not_called()

    def test_registered_disk_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(self.vbox, 'list_vms', return_value=[]), patch.object(self.vbox, 'run', return_value='UUID: '+DISK):
                with self.assertRaisesRegex(VMError, 'disco já registrado'):
                    self.vbox.check_registration(fixture(Path(td)))
