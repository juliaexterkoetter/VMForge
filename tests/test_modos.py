import unittest
from unittest.mock import patch
from vmforge.wizard import escolher_modo, encontrar_porta_livre

class TestarModos(unittest.TestCase):

    def test_basico(self):
        with patch("builtins.input", return_value=""):
            self.assertEqual(escolher_modo(), "basico")

    def test_avancado(self):
        with patch("builtins.input", return_value="2"):
            self.assertEqual(escolher_modo(), "avancado")

    def test_entrada_invalida(self):
        with patch("builtins.input", side_effect=["x", "1"]):
            self.assertEqual(escolher_modo(), "basico")

    def test_porta(self):
        porta = encontrar_porta_livre()
        self.assertGreaterEqual(porta, 2223)
        self.assertLessEqual(porta, 2299)
