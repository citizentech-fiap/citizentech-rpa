"""Respostas RAG simuladas, sem rede nem LLM."""
import copy
import time
import unittest
from unittest.mock import Mock, patch

from robo import responder
from robo.config import load_config


class TestResponder(unittest.TestCase):
    def setUp(self):
        self.estado = responder._RAG, responder._RAG_ERROR
        self.cfg = copy.deepcopy(load_config())
        self.cfg["responder"].update(use_genai=True, llm_timeout_s=0.01)
        self.patcher = patch.object(responder, "load_config", return_value=self.cfg)
        self.patcher.start()
        responder._RAG_ERROR = None
        responder._RAG = Mock()

    def tearDown(self):
        responder._RAG, responder._RAG_ERROR = self.estado
        self.patcher.stop()

    def resposta(self):
        return responder.gerar_resposta("Orientação", self.cfg["services"][0], None, None)

    def test_vazia(self):
        responder._RAG.answer.return_value = {"answer": ""}
        r = self.resposta()
        self.assertEqual((r.fonte, r.motivo_fallback), ("template", "resposta_vazia_ou_abstencao"))

    def test_aviso_inicial_unico(self):
        responder._RAG = None
        responder._RAG_ERROR = "dependência ausente"
        with patch.object(responder.log, "warning") as aviso:
            estado = responder.estado_rag()
            self.resposta()
            self.resposta()
            aviso.assert_called_once()
        self.assertFalse(estado["rag_disponivel"])
        self.assertEqual(estado["motivo_rag"], "dependência ausente")

    def test_desativado_sem_aviso(self):
        self.cfg["responder"]["use_genai"] = False
        with patch.object(responder.log, "warning") as aviso:
            self.assertEqual(responder.estado_rag()["motivo_rag"], "genai_desativado")
            aviso.assert_not_called()

    def test_excecao(self):
        responder._RAG.answer.side_effect = RuntimeError("falha simulada")
        r = self.resposta()
        self.assertEqual((r.fonte, r.motivo_fallback), ("template", "erro_rag: falha simulada"))

    def test_abstencao(self):
        responder._RAG.answer.return_value = {"answer": "Texto", "abstained": True, "reason": "sem_evidencia"}
        r = self.resposta()
        self.assertEqual((r.fonte, r.motivo_fallback), ("template", "sem_evidencia"))

    def test_bloqueio(self):
        responder._RAG.answer.return_value = {"answer": "Texto", "blocked": True, "reason": "bloqueado"}
        r = self.resposta()
        self.assertEqual((r.fonte, r.motivo_fallback), ("template", "bloqueado"))

    def test_timeout(self):
        responder._RAG.answer.side_effect = lambda *a, **k: time.sleep(0.08)
        inicio = time.monotonic()
        r = self.resposta()
        self.assertLess(time.monotonic() - inicio, 0.07)
        self.assertEqual((r.fonte, r.motivo_fallback), ("template", "timeout_rag"))
        time.sleep(0.08)  # deixa o executor compartilhado livre para outros testes

    def test_sucesso_com_citacao(self):
        responder._RAG.answer.return_value = {"answer": "Orientação oficial", "citations": [
            {"n": 1, "titulo": "Carta", "url": "https://www.gov.br/"}]}
        r = self.resposta()
        self.assertEqual((r.fonte, r.motivo_fallback), ("rag", None))
        self.assertIn("Fontes:\n[1] Carta", r.corpo)
