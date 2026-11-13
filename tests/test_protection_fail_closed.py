"""Testes que garantem bloqueio em caso de falha na proteção."""

import unittest
from unittest.mock import patch

from vmforge.providers.virtualbox import VirtualBox, VMError
from vmforge.protection import load_protection


class ProtectionFailClosedTests(unittest.TestCase):

    def setUp(self):
        self.vbox = VirtualBox(binary="fake")

    def test_missing_config_blocks_start(self):
        with patch(
            "vmforge.providers.virtualbox.load_protection",
            side_effect=ValueError("Configuração ausente")
        ), patch(
            "vmforge.providers.virtualbox.subprocess.run"
        ) as process:

            with self.assertRaises(VMError):
                self.vbox.run("startvm", "VM-Teste")

            process.assert_not_called()

    def test_invalid_config_blocks_mutation(self):
        with patch(
            "vmforge.providers.virtualbox.load_protection",
            side_effect=ValueError("Configuração inválida")
        ), patch(
            "vmforge.providers.virtualbox.subprocess.run"
        ) as process:

            with self.assertRaises(VMError):
                self.vbox.run("modifyvm", "VM-Teste", "--memory", "4096")

            process.assert_not_called()

    def test_missing_file_fails_closed(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"

            with self.assertRaises(ValueError):
                load_protection(missing)


if __name__ == "__main__":
    unittest.main()
