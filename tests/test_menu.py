import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from vmforge.cli import main

class TestarMenu(unittest.TestCase):

    def test_menu_em_portugues(self):
        saida = io.StringIO()

        with patch("builtins.input", return_value="0"):
            with redirect_stdout(saida):
                resultado = main([])

        self.assertEqual(resultado, 0)
        self.assertIn("Criar máquina virtual", saida.getvalue())
        self.assertIn("Listar máquinas virtuais", saida.getvalue())
