import unittest
from unittest.mock import patch, call
from vmforge.provisioners.kali import setup_lab

class OptionalFolderTests(unittest.TestCase):
    @patch('vmforge.provisioners.kali.remote_sudo')
    def test_no_folder_operations_by_default(self, sudo):
        setup_lab(object(), 'dummy')
        sudo.assert_not_called()

    @patch('vmforge.provisioners.kali.remote_sudo')
    def test_explicit_folder_opt_in(self, sudo):
        client = object()
        setup_lab(client, 'dummy', create_folders=True)
        self.assertEqual(sudo.call_count, 2)
        self.assertIn('mkdir', sudo.call_args_list[0].args[2])
        self.assertIn('chown', sudo.call_args_list[1].args[2])

if __name__ == '__main__':
    unittest.main()
