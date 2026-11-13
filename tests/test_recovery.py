import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from vmforge.recovery import _check_copy, recover_main, purge_main
from vmforge.wizard import CreationPlan, validate_recovery_plan
from vmforge.config import Settings


class RecoveryTests(unittest.TestCase):
    def test_missing_copy_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises((OSError, ValueError)):
                _check_copy(Path(tmp)/'absent.vbox', Path(tmp))

    def test_outside_destination_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root/'outside.vbox'
            outside.write_bytes(b'no')
            (root/'target').mkdir()
            with self.assertRaisesRegex(ValueError, 'dentro do destino'):
                _check_copy(outside, root/'target')

    def test_uuid_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vbox = root/'test.vbox'
            vdi = root/'test.vdi'
            vbox.write_bytes(b'a')
            vdi.write_bytes(b'b')
            app = {'uuid':'11111111-1111-4111-8111-111111111111',
                   'disk_uuid':'22222222-2222-4222-8222-222222222222', 'disk_path':vdi}
            with patch('vmforge.recovery.validate_appliance', return_value=app), \
                 patch('vmforge.recovery.require_unprotected'):
                with self.assertRaisesRegex(ValueError, 'UUID da copia diferente'):
                    _check_copy(vbox, root, '33333333-3333-4333-8333-333333333333')

    def test_purge_protected_rejected_before_deletion(self):
        with patch('vmforge.recovery.VirtualBox') as factory:
            factory.return_value.require_writable.side_effect = ValueError('protegida')
            with self.assertRaisesRegex(ValueError, 'protegida'):
                purge_main(['--uuid','11111111-1111-4111-8111-111111111111', '--vbox','test.vbox', '--test-root', '.'])

    def test_recovery_without_confirmation_never_executes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vbox = root/'test.vbox'; vbox.write_bytes(b'a')
            disk = root/'test.vdi'; disk.write_bytes(b'b')
            app = {'uuid':'11111111-1111-4111-8111-111111111111',
                   'disk_uuid':'22222222-2222-4222-8222-222222222222', 'disk_path':disk}
            args=['--vbox',str(vbox),'--destination',str(root),
                  '--expected-uuid',app['uuid'],'--expected-disk-uuid',app['disk_uuid'],
                  '--name','VMForge-Recuperada']
            with patch('vmforge.recovery.validate_appliance', return_value=app), \
                 patch('vmforge.recovery.require_unprotected'), \
                 patch('vmforge.recovery.VirtualBox'), \
                 patch('vmforge.recovery.validate_recovery_plan'), \
                 patch('vmforge.recovery.yes', return_value=False), \
                 patch('vmforge.recovery.execute_plan') as execute:
                self.assertEqual(recover_main(args), 0)
                execute.assert_not_called()
