import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from vmforge.config import Settings
from vmforge.wizard import CreationPlan, create_wizard, execute_plan, validate_plan, yes
from vmforge.cli import main
from test_protection import fixture, MACHINE


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root/'original.7z'
        self.image.write_bytes(b'original unchanged')
        self.plan = CreationPlan(Settings(self.image, self.root/'new'), 'Teste', start=False, provision=False, keep_running=False)
        self.vbox = Mock()
        self.vbox.list_vms.return_value = []
        self.vbox.require_writable.return_value = MACHINE
        self.entries = [('kali.vbox', 200, False), ('disk.vdi', 512, False)]

    def test_dry_run_has_no_mutations(self):
        before = list(self.root.iterdir())
        with patch('vmforge.wizard.collect_plan', return_value=self.plan), patch('vmforge.wizard.VirtualBox', return_value=self.vbox), patch('vmforge.wizard.inspect_archive', return_value=self.entries), patch('vmforge.wizard.execute_plan') as execute, patch('vmforge.wizard.getpass.getpass') as password, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(create_wizard(dry_run=True), 0)
            execute.assert_not_called()
            password.assert_not_called()
            self.assertIn('SIMULAÇÃO', out.getvalue())
        self.assertEqual(list(self.root.iterdir()), before)
        self.assertEqual(self.image.read_bytes(), b'original unchanged')
        self.vbox.register.assert_not_called()
        self.vbox.start.assert_not_called()

    def test_cli_dry_run_dispatch(self):
        with patch('vmforge.cli.create_wizard', return_value=0) as wizard:
            self.assertEqual(main(['create', '--dry-run']), 0)
            wizard.assert_called_once_with(dry_run=True)

    def test_confirmation_declined(self):
        with patch('vmforge.wizard.collect_plan', return_value=self.plan), patch('vmforge.wizard.VirtualBox', return_value=self.vbox), patch('vmforge.wizard.inspect_archive', return_value=self.entries), patch('vmforge.wizard.yes', return_value=False), patch('vmforge.wizard.execute_plan') as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(create_wizard(), 0)
            execute.assert_not_called()

    def test_invalid_answers_retry(self):
        with patch('builtins.input', side_effect=['talvez', 's']), redirect_stdout(io.StringIO()):
            self.assertTrue(yes('Confirmar?'))

    def test_registered_name_conflict(self):
        self.vbox.list_vms.return_value = [{'name': 'TESTE', 'uuid': MACHINE}]
        with patch('vmforge.wizard.inspect_archive', return_value=self.entries):
            with self.assertRaisesRegex(ValueError, 'nome'):
                validate_plan(self.plan, self.vbox)

    def test_reserved_port_even_when_vm_stopped(self):
        self.vbox.list_vms.return_value = [{'name': 'Other', 'uuid': MACHINE}]
        self.vbox.info.return_value = {'Forwarding(0)': 'ssh,tcp,127.0.0.1,2223,,22'}
        with patch('vmforge.wizard.inspect_archive', return_value=self.entries):
            with self.assertRaisesRegex(ValueError, 'reservada'):
                validate_plan(self.plan, self.vbox)

    def test_invalid_name(self):
        self.plan.name = '../escape'
        with self.assertRaises(ValueError):
            validate_plan(self.plan, self.vbox)

    def test_invalid_ssh_network(self):
        self.plan.network = 'none'
        self.plan.provision = True
        with self.assertRaises(ValueError):
            validate_plan(self.plan, self.vbox)

    def test_wrong_password_no_preparation(self):
        self.plan.provision = True
        with patch('vmforge.wizard.getpass.getpass', side_effect=['long password1', 'different']), patch('vmforge.wizard.prepare_image') as prepare:
            with self.assertRaises(ValueError):
                execute_plan(self.plan, self.vbox)
            prepare.assert_not_called()

    def test_offline_creation_does_not_start_or_ssh(self):
        path = fixture(self.root)
        with patch('vmforge.wizard.validate_plan'), patch('vmforge.wizard.prepare_image', return_value=path), patch('vmforge.wizard.connect_ssh') as ssh, redirect_stdout(io.StringIO()):
            self.assertEqual(execute_plan(self.plan, self.vbox), 0)
            self.vbox.register.assert_called_once_with(path)
            self.vbox.configure.assert_called_once_with(MACHINE, 4096, 2, 2223, network='nat')
            self.vbox.start.assert_not_called()
            ssh.assert_not_called()

    def test_failure_never_reports_success(self):
        self.vbox.register.side_effect = RuntimeError('registration failed')
        with patch('vmforge.wizard.validate_plan'), patch('vmforge.wizard.prepare_image', return_value=fixture(self.root)), redirect_stdout(io.StringIO()) as out:
            with self.assertRaisesRegex(RuntimeError, 'não concluída.*registro'):
                execute_plan(self.plan, self.vbox)
            self.assertNotIn('CONFIGURAÇÃO CONCLUÍDA', out.getvalue())
            self.vbox.start.assert_not_called()

    def test_snapshot_restart_sequence(self):
        self.plan.start = self.plan.snapshot = self.plan.keep_running = True
        with patch('vmforge.wizard.validate_plan'), patch('vmforge.wizard.prepare_image', return_value=fixture(self.root)), patch('vmforge.wizard.wait_poweroff'), redirect_stdout(io.StringIO()):
            execute_plan(self.plan, self.vbox)
        calls = [c[0] for c in self.vbox.method_calls]
        self.assertLess(calls.index('shutdown'), calls.index('snapshot'))
        self.assertEqual(self.vbox.start.call_count, 2)

    def test_stop_requires_confirmation(self):
        with patch('vmforge.cli.VirtualBox', return_value=self.vbox), patch('vmforge.wizard.yes', return_value=False):
            self.assertEqual(main(['stop', 'Teste']), 0)
            self.vbox.shutdown.assert_not_called()
