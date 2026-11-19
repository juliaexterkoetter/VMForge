"""CLI contract tests; all VirtualBox operations are fakes."""
import io
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from vmforge import cli, import_disk
from vmforge.providers.virtualbox import VMError


class ImportDiskCLITests(unittest.TestCase):
    def setUp(self):
        self.argv = ['import-disk', '--source', 'trusted.vmdk', '--name', 'Nova',
                     '--basefolder', 'base', '--hostonly', 'isolada']
        self.plan = dict(source=Path('trusted.vmdk'), name='Nova', base=Path('base'),
                         target=Path('base/Nova'), hostonly='isolada', ram=512,
                         cpus=1, binary='fake', files={})
        self.planner = self.enterContext(patch('vmforge.import_disk.plan', return_value=self.plan))
        self.execute = self.enterContext(patch('vmforge.import_disk.execute', return_value='Nova'))
        self.input = self.enterContext(patch('builtins.input', return_value='CRIAR'))
        self.vbox = self.enterContext(patch('vmforge.cli.VirtualBox', side_effect=AssertionError('VM real')))
        self.process = self.enterContext(patch('subprocess.run', side_effect=AssertionError('Processo real')))
        self.out, self.err = io.StringIO(), io.StringIO()
        self.enterContext(redirect_stdout(self.out))
        self.enterContext(redirect_stderr(self.err))

    def test_dispatch_preserva_argumentos_e_retorno(self):
        with patch('vmforge.import_disk.main', return_value=7) as handler:
            self.assertEqual(cli.main(self.argv), 7)
        handler.assert_called_once_with(self.argv[1:])
        self.vbox.assert_not_called()

    def test_modulo_encaminha_sys_argv_e_codigo_de_saida(self):
        with patch('sys.argv', ['vmforge', *self.argv]), self.assertRaises(SystemExit) as exit:
            runpy.run_module('vmforge', run_name='__main__')
        self.assertEqual(exit.exception.code, 0)
        self.planner.assert_called_once_with('trusted.vmdk', 'Nova', 'base', 'isolada', 512, 1)
        self.execute.assert_not_called()

    def test_ajuda_em_portugues_sem_planejamento(self):
        with self.assertRaises(SystemExit) as exit:
            cli.main(['import-disk', '--help'])
        self.assertEqual(exit.exception.code, 0)
        for text in ['uso: vmforge import-disk', 'opções:', '--source', '--dry-run',
                     '--execute', 'confirmação', 'Retornos:']:
            self.assertIn(text, self.out.getvalue())
        self.planner.assert_not_called()
        self.execute.assert_not_called()
        self.input.assert_not_called()

    def test_simulacao_padrao_e_explicita_nao_executam_nem_confirmam(self):
        for flags in ([], ['--dry-run']):
            with self.subTest(flags=flags):
                self.assertEqual(cli.main(self.argv + flags), 0)
        self.assertIn('SIMULAÇÃO: nenhuma alteração realizada.', self.out.getvalue())
        self.execute.assert_not_called()
        self.input.assert_not_called()
        self.process.assert_not_called()

    def test_execucao_exige_confirmacao_exata(self):
        for answer in ['', 'sim', 'criar', 'NÃO']:
            with self.subTest(answer=answer):
                self.input.return_value = answer
                self.assertEqual(cli.main(self.argv + ['--execute']), 0)
        self.execute.assert_not_called()
        self.assertIn('Cancelado sem alterações.', self.out.getvalue())
        self.input.return_value = 'CRIAR'
        self.assertEqual(cli.main(self.argv + ['--execute', '--memory', '1024', '--cpus', '2']), 0)
        self.planner.assert_called_with('trusted.vmdk', 'Nova', 'base', 'isolada', 1024, 2)
        self.execute.assert_called_once_with(self.plan)
        self.assertIn('VM criada: Nova', self.out.getvalue())
        self.assertIn('DESLIGADA', self.out.getvalue())

    def test_argumentos_invalidos_retornam_dois_sem_efeitos(self):
        for args in ([], ['--unknown'], self.argv[1:] + ['--memory', 'abc'],
                     self.argv[1:] + ['--dry-run', '--execute']):
            with self.subTest(args=args), self.assertRaises(SystemExit) as exit:
                cli.main(['import-disk', *args])
            self.assertEqual(exit.exception.code, 2)
        self.assertIn('Erro: argumentos inválidos', self.err.getvalue())
        self.planner.assert_not_called()
        self.execute.assert_not_called()

    def test_falhas_no_planejamento_nao_confirmam_nem_executam(self):
        for failure in (ValueError('disco inválido'), VMError('indisponível'),
                        OSError('sem acesso'), RuntimeError('proteção inválida')):
            with self.subTest(failure=failure):
                self.planner.side_effect = failure
                self.assertEqual(cli.main(self.argv + ['--execute']), 1)
        self.input.assert_not_called()
        self.execute.assert_not_called()
        self.assertIn('Erro:', self.err.getvalue())

    def test_interrupcoes_em_todas_as_etapas_sem_traceback(self):
        for stage in (self.planner, self.input, self.execute):
            for interruption in (EOFError, KeyboardInterrupt):
                with self.subTest(stage=stage, interruption=interruption):
                    self.execute.reset_mock()
                    stage.side_effect = interruption
                    self.assertEqual(cli.main(self.argv + ['--execute']), 1)
                    if stage is not self.execute:
                        self.execute.assert_not_called()
                    stage.side_effect = None
        self.assertIn('Importação interrompida', self.err.getvalue())
        self.assertNotIn('Traceback', self.err.getvalue())
        self.assertNotIn('VM criada:', self.out.getvalue())

    def test_falha_de_execucao_retorna_um_sem_sucesso(self):
        self.execute.side_effect = VMError('Configuração parcial')
        self.assertEqual(cli.main(self.argv + ['--execute']), 1)
        self.assertIn('Configuração parcial', self.err.getvalue())
        self.assertNotIn('VM criada:', self.out.getvalue())
