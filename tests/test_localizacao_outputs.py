"""Localização na planilha e no resultado, sem executar o robô completo."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openpyxl import Workbook, load_workbook

from robo.config import load_config
from robo.inbox import Request
from robo.outputs import ControlSheet
from run_robot import processar


class TestLocalizacaoSaidas(unittest.TestCase):
    def test_migra_planilha_e_preserva_historico(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "controle.xlsx"
            wb = Workbook()
            wb.remove(wb.active)
            for nome in ("solicitacoes", "revisao_humana"):
                ws = wb.create_sheet(nome)
                ws.append(["request_id", "motivo"])
                ws.append(["ANTIGO", "histórico preservado"])
            wb.save(arquivo)
            wb.close()
            sheet = ControlSheet(arquivo)
            for nome in ("solicitacoes", "revisao_humana"):
                row = {"request_id": "NOVO", "municipio": "Petrolina", "uf": "PE", "cod_ibge": "2611101"}
                sheet.upsert(nome, row)
                sheet.upsert(nome, {**row, "municipio": "Petrolina atualizado"})
            sheet.save()
            sheet.wb.close()
            lida = load_workbook(arquivo)
            try:
                for nome in ("solicitacoes", "revisao_humana"):
                    ws = lida[nome]
                    header = [c.value for c in ws[1]]
                    self.assertEqual(ws.max_row, 3)
                    self.assertEqual(ws.cell(2, 2).value, "histórico preservado")
                    self.assertEqual(header.count("municipio"), 1)
                    self.assertEqual(ws.cell(3, header.index("municipio") + 1).value, "Petrolina atualizado")
                    celula = ws.cell(3, header.index("cod_ibge") + 1)
                    self.assertEqual(celula.value, "2611101")
                    self.assertEqual(celula.data_type, "s")
            finally:
                lida.close()

    def test_processar_revisao_preserva_localizacao(self):
        req = Request("R1", "Pedido sem serviço identificado", municipio="Caicó", uf="RN", cod_ibge="2402006")
        with mock.patch("run_robot.classifier.predict", return_value=("fora_escopo", 0.9)), \
             mock.patch("run_robot.classifier.predict_top", return_value=[("fora_escopo", 0.9)]), \
             mock.patch("run_robot.responder.resposta_revisao", return_value="Orientação fictícia"), \
             mock.patch("run_robot.outputs.write_eml", return_value=Path("rascunho.eml")):
            resultado = processar(req, {}, load_config())
        self.assertEqual(resultado["decisao"], "revisao_humana")
        self.assertEqual(tuple(resultado[c] for c in ("municipio", "uf", "cod_ibge")), ("Caicó", "RN", "2402006"))


if __name__ == "__main__":
    unittest.main()
