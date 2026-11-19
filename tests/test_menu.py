import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
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

    def test_opcoes_invalidas_permitem_tentar_novamente(self):
        saida = io.StringIO()
        with patch("builtins.input", side_effect=["", "texto", "4", " 0 "]) as entrada:
            with patch("vmforge.cli.VirtualBox") as virtualbox, redirect_stdout(saida):
                resultado = main([])

        self.assertEqual(resultado, 0)
        self.assertEqual(entrada.call_count, 4)
        self.assertEqual(saida.getvalue().count("Opção inválida."), 3)
        self.assertIn("Digite 1, 2, 3 ou 0 para sair.", saida.getvalue())
        virtualbox.assert_not_called()

    def test_opcao_valida_executa_uma_vez_apos_erro(self):
        for opcao, destino in [("1", "create_wizard"), ("3", "check")]:
            with self.subTest(opcao=opcao):
                with patch("builtins.input", side_effect=["9", opcao]):
                    with patch(f"vmforge.cli.{destino}", return_value=7) as acao:
                        with redirect_stdout(io.StringIO()):
                            resultado = main([])
                self.assertEqual(resultado, 7)
                acao.assert_called_once_with()

    def test_listagem_executa_uma_vez_apos_erro(self):
        with patch("builtins.input", side_effect=["9", "2"]):
            with patch("vmforge.cli.VirtualBox") as virtualbox:
                virtualbox.return_value.list_vms.return_value = []
                with redirect_stdout(io.StringIO()):
                    resultado = main([])
        self.assertEqual(resultado, 0)
        virtualbox.assert_called_once_with()
        virtualbox.return_value.list_vms.assert_called_once_with()

    def test_interrupcao_apos_erro_encerra_sem_traceback(self):
        for interrupcao in [EOFError, KeyboardInterrupt]:
            with self.subTest(interrupcao=interrupcao):
                erro = io.StringIO()
                with patch("builtins.input", side_effect=["9", interrupcao]):
                    with redirect_stdout(io.StringIO()), redirect_stderr(erro):
                        resultado = main([])
                self.assertEqual(resultado, 1)
                self.assertIn(interrupcao.__name__, erro.getvalue())
                self.assertNotIn("Traceback", erro.getvalue())
