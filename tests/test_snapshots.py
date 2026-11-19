"""Lab commands tested at the CLI and subprocess boundary; no real VirtualBox."""
import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import Mock, patch

from vmforge.cli import main
from vmforge.protection import ProtectionConfig
from vmforge.providers.virtualbox import VirtualBox

VM = '10000000-0000-4000-8000-000000000001'
SNAP = '20000000-0000-4000-8000-000000000001'
OTHER = '30000000-0000-4000-8000-000000000001'


class LabTests(unittest.TestCase):
    def test_restore_dry_run_does_not_confirm_or_mutate(self):
        with patch('builtins.input', side_effect=AssertionError('prompt forbidden')), redirect_stdout(io.StringIO()):
            self.assertEqual(main(['restore', 'renamed', SNAP, '--dry-run']), 0)
        self.assertEqual(self.mutations, [])

    def test_snapshot_list_is_read_only(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['snapshots', 'renamed']), 0)
        self.assertEqual(json.loads(out.getvalue())['snapshots'], [SNAP])
        self.assertEqual(self.mutations, [])

    def setUp(self):
        self.state = 'poweroff'
        self.snapshots = f'SnapshotName="initial"\nSnapshotUUID="{SNAP}"'
        self.failure = None
        self.mutations = []
        self.protection = ProtectionConfig(frozenset(), frozenset(), frozenset())
        self.vb = VirtualBox(binary='fake-vbox')
        self.process = self.enterContext(patch(
            'vmforge.providers.virtualbox.subprocess.run', side_effect=self.fake_process))
        self.guard = self.enterContext(patch(
            'vmforge.providers.virtualbox.load_protection', return_value=self.protection))
        self.enterContext(patch('vmforge.cli.VirtualBox', return_value=self.vb))

    def fake_process(self, command, **kwargs):
        args = command[1:]
        if args[0] == 'showvminfo':
            return Mock(returncode=0, stdout=(
                f'UUID="{VM}"\nname="renamed"\nVMState="{self.state}"\n'
                'memory=4096\ncpus=2\nSecret="do-not-print"'), stderr='')
        if args == ['snapshot', VM, 'list', '--machinereadable']:
            return Mock(returncode=0, stdout=self.snapshots, stderr='')
        if args[:3] in (['snapshot', VM, 'restore'], ['snapshot', VM, 'take']):
            self.mutations.append(args)
            if self.failure:
                raise self.failure
            return Mock(returncode=0, stdout='', stderr='')
        raise AssertionError(f'Unexpected command: {args}')

    def invoke(self, action='restore', answer=VM, prefix=('lab',)):
        args = [*prefix, action, 'renamed']
        if action == 'restore':
            args.append(SNAP)
        elif action == 'snapshot':
            args.append('initial')
        out, err = io.StringIO(), io.StringIO()
        with patch('builtins.input', side_effect=answer if isinstance(answer, BaseException) else None,
                   return_value=answer), redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_restore_and_alias_use_uuid_and_warn_before_prompt(self):
        for prefix in (('lab',), ()):
            with self.subTest(prefix=prefix):
                code, out, err = self.invoke(prefix=prefix)
                self.assertEqual(code, 0, err)
                self.assertIn('perda do estado atual', out)
                self.assertEqual(self.mutations[-1], ['snapshot', VM, 'restore', SNAP])

    def test_warning_is_visible_before_confirmation(self):
        out = io.StringIO()
        def confirm(prompt):
            self.assertIn('perda do estado atual', out.getvalue())
            self.assertIn(VM, out.getvalue())
            self.assertIn(SNAP, out.getvalue())
            self.assertEqual(self.mutations, [])
            return VM
        with patch('builtins.input', side_effect=confirm), redirect_stdout(out):
            self.assertEqual(main(['lab', 'restore', 'renamed', SNAP]), 0)

    def test_snapshot_and_alias_require_uuid(self):
        for prefix in (('lab',), ()):
            code, _, err = self.invoke('snapshot', prefix=prefix)
            self.assertEqual(code, 0, err)
            self.assertEqual(self.mutations[-1][:4], ['snapshot', VM, 'take', 'initial'])

    def test_cancelled_restore_and_snapshot_never_mutate(self):
        for action in ('restore', 'snapshot'):
            for answer in ('', 'yes', 'sim', 'renamed', OTHER, EOFError(), KeyboardInterrupt()):
                with self.subTest(action=action, answer=answer):
                    code, out, err = self.invoke(action, answer)
                    self.assertEqual(code, 1 if isinstance(answer, BaseException) else 0)
                    self.assertNotIn('concluido', out)
                    self.assertEqual(self.mutations, [])

    def test_non_poweroff_states_never_mutate(self):
        for self.state in ('running', 'paused', 'saved', 'aborted', 'unknown'):
            for action in ('restore', 'snapshot'):
                self.assertEqual(self.invoke(action)[0], 1)
        self.assertEqual(self.mutations, [])

    def test_protection_and_state_rechecked_after_confirmation(self):
        for change in ('protection', 'state'):
            for action in ('restore', 'snapshot'):
                self.guard.return_value = self.protection
                self.state = 'poweroff'
                def confirm(prompt):
                    if change == 'protection':
                        self.guard.return_value = ProtectionConfig(
                            frozenset({VM}), frozenset(), frozenset())
                    else:
                        self.state = 'running'
                    return VM
                target = SNAP if action == 'restore' else 'initial'
                with patch('builtins.input', side_effect=confirm), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(['lab', action, 'renamed', target]), 1)
        self.assertEqual(self.mutations, [])

    def test_invalid_snapshot_uuid_rejected_before_confirmation(self):
        with patch('builtins.input') as confirm, redirect_stderr(io.StringIO()):
            self.assertEqual(main(['lab', 'restore', 'renamed', 'initial']), 1)
        confirm.assert_not_called()
        self.assertEqual(self.mutations, [])

    def test_missing_and_malformed_snapshot_inventory(self):
        for self.snapshots in ('', f'SnapshotUUID="{OTHER}"', 'SnapshotUUID="invalid"'):
            self.assertEqual(self.invoke()[0], 1)
        self.assertEqual(self.mutations, [])

    def test_nested_snapshot_uuid_supported(self):
        self.snapshots = f'SnapshotUUID-1-2="{SNAP}"'
        self.assertEqual(self.invoke()[0], 0)

    def test_protected_uuid_or_name_and_missing_configuration_block_mutations(self):
        for config in (ProtectionConfig(frozenset({VM}), frozenset(), frozenset()),
                       ProtectionConfig(frozenset(), frozenset({'renamed'}), frozenset()),
                       ValueError('Missing config')):
            self.guard.side_effect = config if isinstance(config, Exception) else None
            self.guard.return_value = config
            for action in ('restore', 'snapshot'):
                self.assertEqual(self.invoke(action)[0], 1)
        self.assertEqual(self.mutations, [])

    def test_failed_mutation_is_not_retried_or_reported_as_success(self):
        for action in ('restore', 'snapshot'):
            for self.failure in (OSError('failed'), subprocess.TimeoutExpired('fake', 300), KeyboardInterrupt()):
                self.mutations.clear()
                code, out, err = self.invoke(action)
                self.assertEqual(code, 1)
                self.assertNotIn('concluido', out)
                self.assertNotIn('Snapshot criado', out)
                self.assertEqual(len(self.mutations), 1)

    def test_nonzero_exit_and_inventory_failure(self):
        for failing_operation in ('list', 'restore', 'take'):
            def fail(command, **kwargs):
                if command[1] == 'snapshot' and command[3] == failing_operation:
                    return Mock(returncode=1, stdout='', stderr='fake failure')
                return self.fake_process(command, **kwargs)
            self.process.side_effect = fail
            action = 'snapshot' if failing_operation == 'take' else 'restore'
            code, out, err = self.invoke(action)
            self.assertEqual(code, 1)
            self.assertIn('fake failure', err)
            self.assertNotIn('concluido', out)
            self.assertNotIn('Snapshot criado', out)

    def test_diagnose_read_only_allowlist_even_when_protected(self):
        self.guard.return_value = ProtectionConfig(frozenset({VM}), frozenset(), frozenset())
        code, out, err = self.invoke('diagnose')
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(report['UUID'], VM)
        self.assertEqual(report['snapshots'], [SNAP])
        self.assertEqual(report['protection'], 'protected')
        self.assertNotIn('Secret', report)
        self.assertEqual(self.mutations, [])

    def test_diagnose_missing_protection_is_explicit(self):
        self.guard.side_effect = ValueError('Missing config')
        code, out, err = self.invoke('diagnose', prefix=())
        self.assertEqual(code, 0, err)
        self.assertIn('mutations blocked', json.loads(out)['protection'])

    def test_diagnose_query_failure_returns_error(self):
        self.process.side_effect = OSError('fake failure')
        self.assertEqual(self.invoke('diagnose')[0], 1)
        self.assertEqual(self.mutations, [])
