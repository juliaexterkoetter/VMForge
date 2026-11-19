import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from vmforge import inventory, lab, templates
from vmforge.cli import main
from vmforge.providers.virtualbox import VirtualBox, VMError
from vmforge.protection import ProtectionConfig
import test_import_disk as import_tests


VM = '10000000-0000-4000-8000-000000000001'
OTHER = '20000000-0000-4000-8000-000000000001'


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.vb = Mock()
        self.vb.list_vms.return_value = [{'uuid': VM, 'name': 'test'}]
        self.vb.diagnose.return_value = {'UUID': VM, 'name': 'test', 'snapshots': [], 'protection': 'protected'}
        self.vb.info.return_value = {'UUID': VM, 'nic1': 'hostonly', 'hostonlyadapter1': 'isolated',
                                     'Password': 'TOPSECRET', 'SATA-ImageUUID-0-0': OTHER}

    def test_report_is_structured_and_excludes_secrets(self):
        report = inventory.collect(self.vb)
        self.assertEqual(report['machines'][0]['disks'], [OTHER])
        for fmt in ('json', 'text', 'markdown'):
            rendered = inventory.render(report, fmt)
            self.assertNotIn('TOPSECRET', rendered)
            self.assertIn('isolated', rendered)
        self.assertEqual(json.loads(inventory.render(report, 'json')), report)
        self.vb.require_writable.assert_not_called()

    def test_partial_query_preserves_inventory_and_redacts_error(self):
        self.vb.info.side_effect = VMError('TOPSECRET')
        report = inventory.collect(self.vb)
        self.assertEqual(len(report['problems']), 1)
        self.assertNotIn('TOPSECRET', inventory.render(report, 'json'))

    def test_external_network_is_flagged(self):
        self.vb.info.return_value.update(nic1='bridged')
        self.assertTrue(inventory.collect(self.vb)['machines'][0]['recommendations'])

    def test_cli_dispatch(self):
        with patch('vmforge.inventory.VirtualBox', return_value=self.vb), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['report', '--format', 'json']), 0)
        self.assertEqual(json.loads(out.getvalue())['machines'][0]['UUID'], VM)


class TemplateTests(unittest.TestCase):
    def test_all_templates_reach_lab_planner_with_local_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in templates.CATALOG:
                with redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(main(['template', 'show', name]), 0)
                data = json.loads(out.getvalue())
                for vm in data['vms']:
                    image = root / vm['image']
                    image.parent.mkdir(exist_ok=True)
                    image.write_bytes(b'fixture only; not an appliance')
                manifest = root / 'manifest.json'
                manifest.write_text(json.dumps(data), encoding='utf-8')
                self.assertEqual(len(lab.plan(manifest)['vms']), len(data['vms']))

    def test_executable_fields_and_invalid_resources_rejected(self):
        for vm in ({'name': 'linux', 'image': 'image.7z', 'command': 'execute'},
                   {'name': 'linux', 'image': 'image.7z', 'cpus': True}):
            with self.assertRaises(ValueError):
                templates.validate({'version': 1, 'name': 'demo', 'vms': [vm]})

    def test_lab_inspect_does_not_instantiate_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = {'version': 1, 'name': 'demo', 'uuid': VM, 'network': 'vmforge-' + VM, 'vms': []}
            (root / 'lab.json').write_text(json.dumps(state), encoding='utf-8')
            with patch('vmforge.lab.VirtualBox', side_effect=AssertionError('provider forbidden')), redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(['lab', 'inspect', str(root)]), 0)
            self.assertEqual(json.loads(out.getvalue()), state)
