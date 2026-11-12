import unittest
from vmforge.wizard import planejar_finalizacao

class TestarFinalizacao(unittest.TestCase):

    def test_sem_snapshot_ligada(self):
        resultado = planejar_finalizacao(False, True)
        self.assertFalse(resultado["desligar"])
        self.assertFalse(resultado["snapshot"])

    def test_snapshot_religa(self):
        resultado = planejar_finalizacao(True, True)
        self.assertTrue(resultado["desligar"])
        self.assertTrue(resultado["snapshot"])
        self.assertTrue(resultado["religar"])

    def test_sem_snapshot_desliga(self):
        resultado = planejar_finalizacao(False, False)
        self.assertTrue(resultado["desligar"])
        self.assertFalse(resultado["snapshot"])

    def test_snapshot_desligada(self):
        resultado = planejar_finalizacao(True, False)
        self.assertTrue(resultado["desligar"])
        self.assertFalse(resultado["religar"])
