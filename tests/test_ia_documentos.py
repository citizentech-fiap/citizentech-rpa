"""Testes de privacy, inbox, OCR (identificação de tipo) e classificador.

Executar na pasta RPA:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robo.inbox import load_requests  # noqa: E402
from robo.ocr import check_documents, doc_scores, extract_text, identify_doc_type, OcrResult  # noqa: E402
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
            ok = {"request_id": "R1", "texto": "quero garantia safra", "anexos": ["anexos/a.png", "anexos/nao_existe.png"]}
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

    def test_localizacao_opcional(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            entradas = [
                {"municipio": " Quixadá ", "uf": " CE ", "cod_ibge": "2311306"},
                {},
                {"municipio": None, "uf": "  ", "cod_ibge": None},
                {"cod_ibge": 2611101},
            ]
            for i, local in enumerate(entradas):
                dados = {"request_id": f"R{i}", "texto": "Preciso de orientação sobre o CAF", **local}
                (d / f"R{i}.json").write_text(json.dumps(dados), encoding="utf-8")
            validos, invalidos = load_requests(d)
            self.assertEqual(invalidos, [])
            self.assertEqual((validos[0].municipio, validos[0].uf, validos[0].cod_ibge),
                             ("Quixadá", "CE", "2311306"))
            for req in validos[1:3]:
                self.assertEqual((req.municipio, req.uf, req.cod_ibge), ("", "", ""))
            self.assertEqual(validos[3].cod_ibge, "2611101")
            self.assertEqual(validos[3].municipio, "")

    def test_pasta_inexistente_nao_lanca(self):
        self.assertEqual(load_requests(Path(tempfile.gettempdir()) / "nao_existe_inbox_xyz"), ([], []))


class TestOcr(unittest.TestCase):
    def test_identifica_com_ruido(self):
        self.assertEqual(identify_doc_type("REGISIROGERAL/CARTEIRA DE IDENTIDADE CPF 000")[0], "documento_identidade")
        self.assertEqual(identify_doc_type("COMPROVANTEDEINSCRICAO CADASIRODEPESSOASTISICAS")[0], "cpf")
        self.assertEqual(identify_doc_type(""), (None, 0.0))

    def test_documentos_rurais(self):
        exemplos = [
            ("REGISTRO DE INSCRIÇÃO NO CADASTRO NACIONAL DA AGRICULTURA FAMILIAR - RICAF CPF 000", "caf"),
            ("EXTRATO DO CAF - unidade familiar de produção agrária", "caf"),
            ("REGISTRODEINSCRICAONOCADASIRONACIONALDAAGRICULTURAFAMILIAR RICAF", "caf"),
            ("CONTRATO DE ARRENDAMENTO RURAL CPF 000", "comprovante_posse_terra"),
            ("ESCRITURA PÚBLICA DE IMÓVEL RURAL", "comprovante_posse_terra"),
            ("DECLARAÇÃO DE POSSE - SINDICATO DOS TRABALHADORES RURAIS", "comprovante_posse_terra"),
            ("CONTRATODEARRENDAMENTORURAL", "comprovante_posse_terra"),
            ("ESCRITURA PUBLlCA DE IMOVEL RURAL", "comprovante_posse_terra"),
            ("NOTA FISCAL DE PRODUTOR RURAL CPF 000", "comprovante_renda"),
            ("DECLARAÇÃO DE RENDA", "comprovante_renda"),
        ]
        for texto, esperado in exemplos:
            with self.subTest(texto=texto):
                tipo, score = identify_doc_type(texto)
                self.assertEqual(tipo, esperado)
                self.assertGreaterEqual(score, 0.5)

    def test_catalogo_do_config_limita_tipos(self):
        from robo.config import load_config
        self.assertEqual(set(doc_scores("RICAF")), set(load_config()["document_types"]))
        with mock.patch("robo.ocr.load_config", return_value={"document_types": {"cpf": "CPF"}}):
            self.assertEqual(identify_doc_type("RICAF"), (None, 0.0))
        with mock.patch("robo.ocr.load_config", return_value={"document_types": {}}):
            self.assertEqual(identify_doc_type("RICAF"), (None, 0.0))
        with mock.patch("robo.ocr.load_config", side_effect=OSError("config indisponível")):
            self.assertEqual(identify_doc_type("RICAF"), (None, 0.0))

    def test_conferencia_usa_texto_sem_depender_do_nome(self):
        resultados = [OcrResult("REGISTRO DE INSCRIÇÃO NO CADASTRO NACIONAL DA AGRICULTURA FAMILIAR - RICAF", "teste", True),
                      OcrResult("CONTRATO DE ARRENDAMENTO RURAL - IMÓVEL RURAL", "teste", True)]
        with mock.patch("robo.ocr.extract_text", side_effect=resultados):
            dc = check_documents([Path("arquivo_a.png"), Path("arquivo_b.pdf")], ["caf", "comprovante_posse_terra", "cpf"])
        self.assertEqual(dc.presentes, ["caf", "comprovante_posse_terra"])
        self.assertEqual(dc.faltantes, ["cpf"])
        self.assertEqual(dc.ilegiveis, [])

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
    def test_rejeita_treino_de_outro_catalogo(self):
        from robo.classifier import _carregar_treino
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "treino.csv"
            arquivo.write_text("texto,service_id\nPedido sintético,servico_desativado\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Classes de treino divergentes"):
                _carregar_treino(arquivo)

    def test_modelo_de_outro_catalogo_tenta_retreinar(self):
        from robo import classifier
        antigo = {"pipeline": mock.Mock(classes_=["servico_desativado"])}
        novo = {"pipeline": mock.Mock()}

        def treinar():
            classifier._MODELO = novo

        with mock.patch.object(classifier, "_MODELO", None), \
             mock.patch.object(classifier, "_caminho_modelo", return_value=mock.Mock(is_file=lambda: True)), \
             mock.patch("joblib.load", return_value=antigo), \
             mock.patch.object(classifier, "train", side_effect=treinar) as treino:
            self.assertIs(classifier._obter_modelo(), novo)
            treino.assert_called_once_with()

    def test_predict(self):
        from robo.classifier import predict
        exemplos = {
            "quero receber o garantia safra, minha plantação secou": "garantia_safra",
            "preciso fazer meu cadastro nacional da agricultura familiar CAF": "caf",
            "quero um empréstimo de custeio pelo pronaf no banco": "pronaf",
            "trabalhei a vida toda na roça e quero aposentadoria rural": "aposentadoria_rural",
            "sou agricultora e quero salário maternidade rural": "salario_maternidade_rural",
            "quero fazer cadastro único no CRAS": "cadunico",
            "meu bolsa família foi bloqueado, quero voltar a receber": "bolsa_familia",
            "quero benefício de prestação continuada BPC LOAS": "bpc",
            "preciso regularizar meu CPF suspenso": "cpf",
            "quero consertar a estrada do sítio, tem buracos": "fora_escopo",
        }
        for texto, esperado in exemplos.items():
            with self.subTest(servico=esperado):
                sid, conf = predict(texto)
                self.assertEqual(sid, esperado)
                if esperado != "fora_escopo":  # fora do escopo vai para revisão humana com qualquer confiança
                    self.assertGreater(conf, 0.45)
        self.assertEqual(predict(""), (None, 0.0))


if __name__ == "__main__":
    unittest.main()
