"""Lab commands use a fake provider and archive extractor exclusively."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from vmforge import lab
from vmforge.cli import main
from vmforge.providers.virtualbox import VirtualBox, VMError
from test_protection import fixture, TEST_PROTECTION


class FakeBox:
    def __init__(self):
        self.machines = {}
        self.calls = []
        self.fail = None

    def list_vms(self):
        return [dict(name=v['name'], uuid=k) for k, v in self.machines.items()]

    def register(self, path):
        appliance = lab.validate_appliance(path)
        root = ET.parse(path).getroot()
        adapters = [e for e in root.iter() if e.tag.endswith('Adapter')]
        assert len(adapters) == 1
        net = next(e for e in root.iter() if e.tag.endswith('InternalNetwork'))
        info = dict(UUID=appliance['uuid'], name=appliance['name'], CfgFile=str(path),
                    VMState='poweroff', nic1='intnet', intnet1=net.get('name'))
        info.update({f'nic{i}': 'none' for i in range(2, 9)})
        self.machines[appliance['uuid']] = info
        self.calls.append(('register', appliance['uuid']))
        if self.fail == 'register':
            raise VMError('registration timeout after success')

    def configure_lab(self, identity, ram, cpus, network):
        self.calls.append(('configure', identity))
        if self.fail == 'configure':
            raise VMError('configure failed')

    def info(self, identity):
        if identity not in self.machines:
            raise VMError('VM missing')
        return self.machines[identity].copy()

    def require_writable(self, identity):
        lab.require_unprotected(identity, self.machines[identity]['name'])
        return identity

    def start(self, identity):
        self.calls.append(('start', identity))
        if self.fail == ('start', identity):
            raise VMError('start failed')
        self.machines[identity]['VMState'] = 'running'
        return 'running'

    def shutdown(self, identity):
        self.calls.append(('stop', identity))
        if self.fail == ('stop', identity):
            raise VMError('stop failed')
        return 'Desligamento solicitado (ACPI).'


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.image = self.root / 'template.7z'
        self.image.write_bytes(b'original archive')
        self.manifest = self.root / 'manifest.json'
        self.document = dict(version=1, name='training', vms=[
            dict(name='attacker', image='template.7z'),
            dict(name='target', image='template.7z', ram=2048, cpus=1)])
        self.write_manifest()
        self.directory = self.root / 'lab'
        self.vb = FakeBox()
        for target, kwargs in [
            ('vmforge.lab.VirtualBox', dict(return_value=self.vb)),
            ('vmforge.lab.extract_archive', dict(side_effect=self.extract)),
            ('vmforge.protection.load_protection', dict(return_value=TEST_PROTECTION)),
            ('subprocess.run', dict(side_effect=AssertionError('External process forbidden'))),
            ('subprocess.Popen', dict(side_effect=AssertionError('External process forbidden'))),
        ]:
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def extract(self, image, directory):
        directory.mkdir()
        fixture(directory, extra='<Network><Adapter slot="0"><NAT/></Adapter><Adapter slot="1"><BridgedInterface name="host"/></Adapter></Network>')

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.document), encoding='utf-8')

    def call(self, action, *options):
        subject = self.manifest if action in ('plan', 'create') else self.directory
        args = ['lab', action, str(subject)]
        if action == 'create':
            args += ['--directory', str(self.directory)]
        with patch('sys.stdout', new_callable=io.StringIO) as out, patch('sys.stderr', new_callable=io.StringIO) as err:
            code = main(args + list(options))
        self.output = out.getvalue() + err.getvalue()
        return code

    def create(self):
        self.assertEqual(self.call('create', '--yes'), 0, self.output)
        return lab.load_state(self.directory)

    def test_plan_is_offline_and_does_not_write(self):
        before = set(self.root.rglob('*'))
        with patch('vmforge.lab.VirtualBox', side_effect=AssertionError('provider forbidden')):
            self.assertEqual(self.call('plan'), 0)
        self.assertEqual(set(self.root.rglob('*')), before)
        self.assertIn('interna exclusiva', self.output)

    def test_plan_rejects_bad_manifests(self):
        for change in (dict(version=2), dict(version=True), dict(vms=[]), dict(extra=1), dict(name='../escape'),
                       dict(vms=[dict(name='a', image='missing.7z')]),
                       dict(vms=[dict(name='a', image='template.7z', cpus=True)]),
                       dict(vms=[dict(name='a', image='template.7z'), dict(name='A', image='template.7z')])):
            with self.subTest(change=change):
                doc = dict(self.document, **change)
                self.manifest.write_text(json.dumps(doc), encoding='utf-8')
                self.assertEqual(self.call('plan'), 1)
        self.assertFalse(self.directory.exists())

    def test_plan_rejects_duplicate_json_keys(self):
        self.manifest.write_text('{"version":1,"version":2}', encoding='utf-8')
        self.assertEqual(self.call('plan'), 1)

    def test_create_records_independent_uuids_and_internal_network(self):
        state = self.create()
        self.assertEqual(len({v['uuid'] for v in state['vms']}), 2)
        self.assertEqual(len({v['disk_uuid'] for v in state['vms']}), 2)
        for vm in state['vms']:
            self.assertEqual(vm['phase'], 'ready')
            self.assertEqual(lab.verify(self.vb, vm, state['network']), 'poweroff')
        self.assertEqual(self.image.read_bytes(), b'original archive')
        self.assertFalse(any(c[0] == 'start' for c in self.vb.calls))

    def test_create_requires_confirmation_and_never_reuses_destination(self):
        with patch('builtins.input', return_value='nao'):
            self.assertEqual(self.call('create'), 0)
        self.assertFalse(self.directory.exists())
        self.create()
        before = (self.directory / 'lab.json').read_bytes()
        self.assertEqual(self.call('create', '--yes'), 1)
        self.assertEqual((self.directory / 'lab.json').read_bytes(), before)

    def test_create_partial_registration_keeps_uuid_and_blocks_start(self):
        self.vb.fail = 'register'
        self.assertEqual(self.call('create', '--yes'), 1)
        state = lab.load_state(self.directory)
        vm = state['vms'][0]
        self.assertEqual(vm['phase'], 'registering')
        self.assertIn(vm['uuid'], self.vb.machines)
        self.assertIn('timeout', vm['error'])
        self.assertEqual(self.call('start', '--yes'), 1)
        self.assertFalse(any(c[0] == 'start' for c in self.vb.calls))

    def test_create_configuration_failure_is_durable(self):
        self.vb.fail = 'configure'
        self.assertEqual(self.call('create', '--yes'), 1)
        self.assertEqual(lab.load_state(self.directory)['vms'][0]['phase'], 'configuring')

    def test_create_extraction_failure_is_durable(self):
        with patch('vmforge.lab.extract_archive', side_effect=ValueError('bad archive')):
            self.assertEqual(self.call('create', '--yes'), 1)
        vm = lab.load_state(self.directory)['vms'][0]
        self.assertIsNone(vm['uuid'])
        self.assertIn('bad archive', vm['error'])
        self.assertEqual(self.vb.calls, [])

    def test_start_uses_uuids_and_rejects_network_drift(self):
        state = self.create()
        self.assertEqual(self.call('start', '--yes'), 0)
        self.assertEqual([v[1] for v in self.vb.calls if v[0] == 'start'], [v['uuid'] for v in state['vms']])
        self.vb.calls.clear()
        self.vb.machines[state['vms'][0]['uuid']]['nic2'] = 'nat'
        self.assertEqual(self.call('start', '--yes'), 1)
        self.assertEqual(self.vb.calls, [])

    def test_start_failure_stops_batch_and_journals_result(self):
        state = self.create()
        identity = state['vms'][0]['uuid']
        self.vb.fail = ('start', identity)
        self.assertEqual(self.call('start', '--yes'), 1)
        self.assertEqual([c for c in self.vb.calls if c[0] == 'start'], [('start', identity)])
        self.assertEqual(lab.load_state(self.directory)['vms'][0]['result'], 'failed-or-uncertain')

    def test_start_and_stop_require_confirmation(self):
        self.create()
        self.vb.calls.clear()
        for action in ('start', 'stop'):
            with patch('builtins.input', return_value='no'):
                self.assertEqual(self.call(action), 0)
        self.assertEqual(self.vb.calls, [])

    def test_status_read_only_and_missing_vm_reports_failure(self):
        state = self.create()
        before = (self.directory / 'lab.json').read_bytes()
        self.vb.calls.clear()
        self.assertEqual(self.call('status'), 0)
        self.assertIn('poweroff', self.output)
        del self.vb.machines[state['vms'][0]['uuid']]
        self.assertEqual(self.call('status'), 1)
        self.assertIn('training-target', self.output)
        self.assertEqual((self.directory / 'lab.json').read_bytes(), before)
        self.assertEqual(self.vb.calls, [])

    def test_stop_requests_acpi_and_continues_after_partial_failure(self):
        state = self.create()
        self.assertEqual(self.call('start', '--yes'), 0)
        self.vb.fail = ('stop', state['vms'][0]['uuid'])
        self.assertEqual(self.call('stop', '--yes'), 1)
        self.assertEqual(len([c for c in self.vb.calls if c[0] == 'stop']), 2)
        self.assertIn('solicitado', self.output)
        self.assertTrue(all(v['VMState'] == 'running' for v in self.vb.machines.values()))

    def test_stop_powered_off_is_noop(self):
        self.create()
        self.assertEqual(self.call('stop', '--yes'), 0)
        self.assertFalse(any(c[0] == 'stop' for c in self.vb.calls))

    def test_identity_mismatch_blocks_mutation(self):
        state = self.create()
        self.vb.calls.clear()
        self.vb.machines[state['vms'][0]['uuid']]['name'] = 'other'
        self.assertEqual(self.call('start', '--yes'), 1)
        self.assertEqual(self.vb.calls, [])

    def test_lock_and_corrupt_registry_fail_closed(self):
        self.create()
        (self.directory / '.lab.lock').write_text('other process')
        self.assertEqual(self.call('start', '--yes'), 1)
        (self.directory / 'lab.json').write_text('{invalid')
        self.assertEqual(self.call('status'), 1)

    def test_journal_failure_prevents_registration(self):
        with patch('vmforge.lab.save', side_effect=OSError('disk full')):
            self.assertEqual(self.call('create', '--yes'), 1)
        self.assertEqual(self.vb.calls, [])

    def test_start_journal_failure_prevents_mutation(self):
        self.create()
        self.vb.calls.clear()
        with patch('vmforge.lab.save', side_effect=OSError('disk full')):
            self.assertEqual(self.call('start', '--yes'), 1)
        self.assertEqual(self.vb.calls, [])

    def test_create_second_vm_failure_preserves_first_and_full_inventory(self):
        original = self.extract
        def extract(image, directory):
            if directory.name == 'target':
                raise ValueError('second archive failed')
            return original(image, directory)
        with patch('vmforge.lab.extract_archive', side_effect=extract):
            self.assertEqual(self.call('create', '--yes'), 1)
        state = lab.load_state(self.directory)
        self.assertEqual(len(state['vms']), 2)
        self.assertEqual(state['vms'][0]['phase'], 'ready')
        self.assertIsNone(state['vms'][1]['uuid'])
        self.assertEqual(len(self.vb.machines), 1)
        self.assertEqual(self.call('status'), 1)

    def test_protected_vm_blocks_start(self):
        from vmforge.protection import ProtectionConfig
        state = self.create()
        self.vb.calls.clear()
        cfg = ProtectionConfig(frozenset({state['vms'][0]['uuid']}), frozenset(), frozenset())
        with patch('vmforge.protection.load_protection', return_value=cfg):
            self.assertEqual(self.call('start', '--yes'), 1)
        self.assertEqual(self.vb.calls, [])

    def test_corrupt_state_uuid_and_path_fail_closed(self):
        state = self.create()
        for key, value in (('uuid', 'bad-uuid'), ('path', str(self.root / 'outside.vbox'))):
            with self.subTest(key=key):
                altered = json.loads(json.dumps(state))
                altered['vms'][0][key] = value
                lab.save(self.directory / 'lab.json', altered)
                self.assertEqual(self.call('start', '--yes'), 1)


class LabProviderTests(unittest.TestCase):
    def test_configure_lab_disables_every_other_adapter(self):
        vb = VirtualBox(binary='fake')
        identity = '10000000-0000-4000-8000-000000000001'
        with patch.object(vb, 'status', return_value='poweroff'), patch.object(vb, 'run') as run:
            vb.configure_lab(identity, 4096, 2, 'vmforge-' + identity)
        args = run.call_args.args
        self.assertEqual(args[:2], ('modifyvm', identity))
        self.assertEqual(args[args.index('--nic1') + 1], 'intnet')
        for i in range(2, 9):
            self.assertEqual(args[args.index(f'--nic{i}') + 1], 'none')

    def test_configure_lab_rejects_running_vm(self):
        vb = VirtualBox(binary='fake')
        identity = '10000000-0000-4000-8000-000000000001'
        with patch.object(vb, 'status', return_value='running'), patch.object(vb, 'run') as run:
            with self.assertRaises(VMError):
                vb.configure_lab(identity, 4096, 2, 'vmforge-' + identity)
        run.assert_not_called()
