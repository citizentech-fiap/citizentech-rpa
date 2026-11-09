"""Fechamento auditável em planilha temporária."""
import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from robo.outputs import ControlSheet
from robo.revisao import fechar, listar, main


class TestRevisao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.tmp.name) / "controle.xlsx"
        planilha = ControlSheet(self.arquivo)
        planilha.upsert("revisao_humana", {"request_id": "REQ-0011", "status": "pendente", "municipio": "Petrolina"})
        planilha.save()
        planilha.wb.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fechar_e_nao_reabrir(self):
        self.assertEqual(len(listar(self.arquivo)), 1)
        fechar("REQ-0011", "respondido", "Atendente Fictício", "Teste", self.arquivo)
        self.assertEqual(listar(self.arquivo), [])
        planilha = ControlSheet(self.arquivo)
        planilha.upsert("revisao_humana", {"request_id": "REQ-0011", "status": "pendente"})
        planilha.save()
        planilha.wb.close()
        wb = load_workbook(self.arquivo)
        linhas = list(wb["revisao_humana"].values)
        registro = dict(zip(*linhas))
        self.assertEqual(registro["status"], "fechado")
        self.assertEqual(registro["desfecho"], "respondido")
        self.assertEqual(registro["municipio"], "Petrolina")
        self.assertEqual(registro["observacao"], "Teste")
        self.assertTrue(registro["fechado_em"])
        wb.close()

    def test_erros_nao_alteram_planilha(self):
        for pedido, responsavel in [("ausente", "Teste"), ("REQ-0011", " ")]:
            antes = self.arquivo.read_bytes()
            self.assertNotEqual(main(["--fechar", pedido, "--desfecho", "respondido", "--responsavel", responsavel,
                                      "--planilha", str(self.arquivo)]), 0)
            self.assertEqual(antes, self.arquivo.read_bytes())
        fechar("REQ-0011", "encaminhado", "Teste", arquivo=self.arquivo)
        antes = self.arquivo.read_bytes()
        with self.assertRaisesRegex(ValueError, "já fechado"):
            fechar("REQ-0011", "indeferido", "Outro", arquivo=self.arquivo)
        self.assertEqual(antes, self.arquivo.read_bytes())
