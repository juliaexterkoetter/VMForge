import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from vmforge.resume import verify_registered_copy, resume_main


IDENTITY='d783d82a-5164-4d28-814e-e68adefe04fe'
DISK='ae5eefc4-6e32-4744-8148-f688c73a7656'


class ResumeTests(unittest.TestCase):
    def test_wrong_name_rejected_before_modification(self):
        vb=Mock()
        with self.assertRaisesRegex(ValueError, 'Somente VMs'):
            verify_registered_copy(vb,IDENTITY,'test.vbox',DISK,'kali-linux-2026.3')
        vb.require_writable.assert_not_called()

    def test_protected_uuid_rejected(self):
        vb=Mock()
        vb.require_writable.side_effect=ValueError('protegida')
        with self.assertRaisesRegex(ValueError,'protegida'):
            verify_registered_copy(vb,IDENTITY,'test.vbox',DISK,'VMForge-Recuperada')

    def test_dry_run_does_not_execute_guestcontrol(self):
        with patch('vmforge.resume.VirtualBox') as factory, \
             patch('vmforge.resume.verify_registered_copy',return_value=IDENTITY), \
             patch('vmforge.resume.getpass.getpass') as getpass, \
             patch('vmforge.resume.guest_run') as guest:
            vb=factory.return_value
            vb.info.return_value={'Forwarding(0)':'vmforge-ssh,tcp,127.0.0.1,2224,,22'}
            rc=resume_main(['--uuid',IDENTITY,'--vbox','test.vbox',
                            '--expected-disk-uuid',DISK,'--name','VMForge-Recuperada',
                            '--port','2224','--dry-run'])
            self.assertEqual(rc,0)
            getpass.assert_not_called()
            guest.assert_not_called()

    def test_reject_bad_port(self):
        with self.assertRaisesRegex(ValueError,'Porta'):
            resume_main(['--uuid',IDENTITY,'--vbox','test.vbox',
                         '--expected-disk-uuid',DISK,'--name','VMForge-Recuperada',
                         '--port','22','--dry-run'])

    def test_name_and_disk_mismatch_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'test.vbox';path.write_bytes(b'fixture')
            disk=Path(td)/'test.vdi';disk.write_bytes(b'x')
            vb=Mock()
            vb.require_writable.return_value=IDENTITY
            vb.info.return_value={'CfgFile':str(path),'name':'VMForge-Recuperada'}
            app={'uuid':IDENTITY,'disk_uuid':DISK,'name':'VMForge-Recuperada','disk_path':disk}
            protection=Mock();protection.protects_vm.return_value=False
            with patch('vmforge.resume.validate_appliance',return_value=app),patch('vmforge.resume.load_protection',return_value=protection):
                with self.assertRaisesRegex(ValueError,'Nome ou UUID'):
                    verify_registered_copy(vb,IDENTITY,path,'11111111-1111-4111-8111-111111111111','VMForge-Recuperada')
