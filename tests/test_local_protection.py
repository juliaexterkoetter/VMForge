import json
import tempfile
import unittest
from pathlib import Path

from vmforge.protection import load_protection


UUID_PROTEGIDO = "11111111-2222-4333-8444-555555555555"
UUID_LIVRE = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


class LocalProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_protects_by_uuid_even_if_renamed(self):
        self.write({
            "protected_vms": [
                {"name": "Laboratorio", "uuid": UUID_PROTEGIDO}
            ],
            "reserved_ports": [2222]
        })

        config = load_protection(self.path)

        self.assertTrue(config.protects_vm(UUID_PROTEGIDO, "OutroNome"))
        self.assertTrue(config.protects_vm(UUID_LIVRE, "Laboratorio"))
        self.assertFalse(config.protects_vm(UUID_LIVRE, "NovaVM"))
        self.assertTrue(config.reserves_port(2222))
        self.assertFalse(config.reserves_port(2223))

    def test_missing_configuration_blocks(self):
        with self.assertRaises(ValueError):
            load_protection(self.path)

    def test_invalid_json_blocks(self):
        self.path.write_text("{invalido", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_protection(self.path)

    def test_invalid_uuid_blocks(self):
        self.write({
            "protected_vms": [{"name": "Teste", "uuid": "invalido"}],
            "reserved_ports": [2222]
        })
        with self.assertRaises(ValueError):
            load_protection(self.path)

    def test_invalid_port_blocks(self):
        self.write({
            "protected_vms": [],
            "reserved_ports": [70000]
        })
        with self.assertRaises(ValueError):
            load_protection(self.path)


if __name__ == "__main__":
    unittest.main()
