import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from vmforge.config import Settings, validate
from vmforge.providers.virtualbox import VirtualBox, VMError
from vmforge.cli import main


class SettingsTests(unittest.TestCase):
    def test_invalid_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                validate(Settings(Path(td) / 'missing.7z', Path(td) / 'dest'))

    def test_ram_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / 'kali.7z'
            img.touch()
            with self.assertRaisesRegex(ValueError, 'RAM'):
                validate(Settings(img, Path(td) / 'new', ram=100))

    def test_destination_existing_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / 'kali.7z'
            img.touch()
            with self.assertRaisesRegex(ValueError, 'pasta de destino'):
                validate(Settings(img, Path(td)))


class VirtualBoxTests(unittest.TestCase):
    def test_list_parse(self):
        vm = VirtualBox(binary='/fake/VBoxManage')
        with patch.object(vm, 'run', return_value='"Kali-Lab" {2d792251-94c7-41f0-95e5-5ebf008983b2}\n'):
            self.assertEqual(vm.list_vms()[0]['name'], 'Kali-Lab')

    def test_start_does_not_repeat(self):
        vm = VirtualBox(binary='/fake/VBoxManage')
        with patch.object(vm, 'status', return_value='running'):
            with patch.object(vm, 'run') as mocked:
                self.assertIn('já está ligada', vm.start('Kali'))
                mocked.assert_not_called()

    def test_start_unexpected_state_rejected(self):
        vm = VirtualBox(binary='/fake/VBoxManage')
        with patch.object(vm, 'status', return_value='saved'):
            with self.assertRaises(VMError):
                vm.start('Kali')

    def test_status_parse(self):
        vm = VirtualBox(binary='/fake/VBoxManage')
        with patch.object(vm, 'run', return_value='VMState="poweroff"\nmemory=4096'):
            self.assertEqual(vm.status('Kali'), 'poweroff')


class CliTests(unittest.TestCase):
    def test_help(self):
        with self.assertRaises(SystemExit) as cm:
            main(['--help'])
        self.assertEqual(cm.exception.code, 0)

    def test_version(self):
        with self.assertRaises(SystemExit) as cm:
            main(['--version'])
        self.assertEqual(cm.exception.code, 0)


if __name__ == '__main__':
    unittest.main()
