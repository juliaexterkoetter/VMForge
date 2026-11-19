"""Read-only tests for VMDK import planning."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from vmforge.import_disk import plan
from vmforge.protection import ProtectionConfig


class ImportPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'trusted.vmdk'
        self.src.write_bytes(b'placeholder')  # planning does not open image content
        self.vb = Mock()
        self.vb.list_vms.return_value = []
        self.vb.binary = 'VBoxManage'
        self.cfg = ProtectionConfig(frozenset(), frozenset(), frozenset({2222}))

    def invoke(self, **overrides):
        args = dict(source=self.src, name='TestTarget', basefolder=self.root,
                    hostonly='VirtualBox Host-Only Ethernet Adapter', vb=self.vb)
        args.update(overrides)
        with patch('vmforge.import_disk.load_protection', return_value=self.cfg), \
             patch('vmforge.import_disk._call', return_value='Name:            VirtualBox Host-Only Ethernet Adapter\n'):
            return plan(**args)

    def test_valid_dry_plan(self):
        p = self.invoke()
        self.assertEqual(p['name'], 'TestTarget')
        self.assertFalse(p['target'].exists())

    def test_existing_target_rejected(self):
        (self.root / 'TestTarget').mkdir()
        with self.assertRaises(ValueError):
            self.invoke()

    def test_existing_vm_rejected(self):
        self.vb.list_vms.return_value = [{'name': 'testtarget', 'uuid': 'abc'}]
        with self.assertRaises(ValueError):
            self.invoke()

    def test_non_vmdk_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke(source=self.root / 'not-found.vmdk')

    def test_protected_name_rejected(self):
        self.cfg = ProtectionConfig(frozenset(), frozenset({'testtarget'}), frozenset())
        with self.assertRaises(ValueError):
            self.invoke()


if __name__ == '__main__':
    unittest.main()
