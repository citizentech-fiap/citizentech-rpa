"""Testes de privacy, inbox, OCR (identificação de tipo) e classificador.

Executar na pasta RPA:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robo.inbox import load_requests  # noqa: E402
from robo.ocr import check_documents, extract_text, identify_doc_type  # noqa: E402
from robo.privacy import mask_pii  # noqa: E402


class TestPrivacy(unittest.TestCase):
    def test_mascara_dados(self):
        s = mask_pii("CPF 123.456.789-09, e-mail fulano@exemplo.com, cel (11) 98765-4321, RG: 12.345.678-9")
        self.assertEqual(s, "CPF [CPF], e-mail [EMAIL], cel [TELEFONE], RG: [RG]")
        self.assertIn("[CPF]", mask_pii("meu cpf 12345678909"))
        self.assertIn("[TELEFONE]", mask_pii("whats 11987654321"))
        self.assertIn("[TELEFONE]", mask_pii("+55 11 3456-7890"))

    def test_nao_mascara_numeros_comuns(self):
        s = "Trabalhei de 2019 a 2024, 2 meses, R$ 1.412,00, em 05/11/2026, CEP 01310-100, ano 2025-2026"
        self.assertEqual(mask_pii(s), s)
        self.assertEqual(mask_pii(""), "")


class TestInbox(unittest.TestCase):
    def test_validacoes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "anexos").mkdir()
            (d / "anexos" / "a.png").write_bytes(b"x")
            ok = {"request_id": "R1", "texto": "quero o seguro", "anexos": ["anexos/a.png", "anexos/nao_existe.png"]}
            (d / "R1.json").write_text(json.dumps(ok), encoding="utf-8")
            (d / "R2.json").write_text('{"request_id": "R2", "texto": ', encoding="utf-8")
            (d / "R3.json").write_text(json.dumps({"request_id": "R3", "texto": "  "}), encoding="utf-8")
            (d / "R4.json").write_text(json.dumps({"request_id": "R1", "texto": "dup"}), encoding="utf-8")
            (d / "R5.json").write_text(json.dumps({"request_id": "R5", "texto": "x", "anexos": ["../../fora.png"]}),
                                       encoding="utf-8")
            validos, invalidos = load_requests(d)
            self.assertEqual(sorted(r.request_id for r in validos), ["R1", "R5"])
            r1 = next(r for r in validos if r.request_id == "R1")
            self.assertEqual(len(r1.anexos_abs), 1)
            self.assertEqual(r1.anexos_ausentes, ["anexos/nao_existe.png"])
            r5 = next(r for r in validos if r.request_id == "R5")
            self.assertEqual(r5.anexos_ausentes, ["../../fora.png"])
            self.assertEqual(len(invalidos), 3)

    def test_pasta_inexistente_nao_lanca(self):
        self.assertEqual(load_requests(Path(tempfile.gettempdir()) / "nao_existe_inbox_xyz"), ([], []))


class TestOcr(unittest.TestCase):
    def test_identifica_com_ruido(self):
        self.assertEqual(identify_doc_type("REGISIROGERAL/CARTEIRA DE IDENTIDADE CPF 000")[0], "documento_identidade")
        self.assertEqual(identify_doc_type("COMPROVANTEDEINSCRICAO CADASIRODEPESSOASTISICAS")[0], "cpf")
        self.assertEqual(identify_doc_type("Termo de Rescisão do Contrato de Trabalho - CTPS 123")[0], "termo_rescisao")
        self.assertEqual(identify_doc_type("CARTEIRA DE TRABALHO E PREVIDENCIA SOCIAL")[0], "carteira_trabalho")
        self.assertEqual(identify_doc_type(""), (None, 0.0))

    def test_arquivo_ausente_ou_corrompido(self):
        self.assertFalse(extract_text("nao_existe.png").ok)
        with tempfile.TemporaryDirectory() as tmp:
            ruim = Path(tmp) / "corrompido.png"
            ruim.write_bytes(b"isto nao e uma imagem")
            self.assertFalse(extract_text(ruim).ok)
            dc = check_documents([ruim], ["cpf"])
            self.assertEqual(dc.faltantes, ["cpf"])
            self.assertEqual(dc.ilegiveis, ["corrompido.png"])


class TestClassificador(unittest.TestCase):
    def test_predict(self):
        from robo.classifier import predict
        sid, conf = predict("fui demitido sem justa causa, como peço o seguro-desemprego?")
        self.assertEqual(sid, "seguro_desemprego")
        self.assertGreater(conf, 0.45)
        self.assertEqual(predict(""), (None, 0.0))


if __name__ == "__main__":
    unittest.main()
