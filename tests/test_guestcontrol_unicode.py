import unittest
from unittest.mock import patch
from types import SimpleNamespace
from vmforge.providers.virtualbox import VirtualBox, VMError

class UnicodeGuestTests(unittest.TestCase):
    def setUp(self):
        self.vb=VirtualBox(binary='VBoxManage.exe')
        self.uuid='11111111-1111-4111-8111-111111111111'
    def test_utf8_decoding_requested(self):
        result=SimpleNamespace(returncode=0,stdout='máquina',stderr='')
        with patch('vmforge.providers.virtualbox.subprocess.run', return_value=result) as proc:
            self.assertEqual(self.vb.run('showvminfo',self.uuid),'máquina')
            self.assertEqual(proc.call_args.kwargs['encoding'],'utf-8')
            self.assertEqual(proc.call_args.kwargs['errors'],'strict')
    def test_allowed_guest_control_guarded(self):
        result=SimpleNamespace(returncode=0,stdout='kali',stderr='')
        args=('guestcontrol',self.uuid,'run','--exe','/usr/bin/id','--username','kali','--passwordfile','test.pass','--wait-stdout','--','-un')
        with patch.object(self.vb,'require_writable',return_value=self.uuid) as guard, patch('vmforge.providers.virtualbox.subprocess.run',return_value=result):
            self.assertEqual(self.vb.run(*args),'kali')
            guard.assert_called_once_with(self.uuid)
    def test_unsafe_guest_control_denied(self):
        with self.assertRaises(VMError): self.vb.run('guestcontrol',self.uuid,'copyto','x')
        with self.assertRaises(VMError): self.vb.run('guestcontrol',self.uuid,'run','--exe','/bin/sh','--username','kali','--passwordfile','x')
    def test_delete_not_allowed_through_provider(self):
        with self.assertRaises(VMError): self.vb.run('unregistervm',self.uuid,'--delete')
