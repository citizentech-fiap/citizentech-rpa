"""Testes do coletor sem acesso à rede (HTTP simulado).

Rodar a partir de RPA/:  ..\\.venv\\Scripts\\python -m unittest tests.test_collector -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from robo import collector as col

SID = "seguro_desemprego"

HTML_CARTA = """<html><head><meta name="identificador" content="1045" /></head><body>
<div class="visao-servico"><div class="titulo">Solicitar o Seguro-Desemprego
<span class="nomes-populares">seguro</span></div></div>
<div class="servico-content"><ul class="servico">
 <li><a class="titulo" id="dados_basicos">O que é?</a><div class="conteudo"><p>Assistência financeira temporária
 ao trabalhador dispensado sem justa causa. Texto longo o bastante para passar na validação de conteúdo mínimo.</p></div></li>
 <li><a class="titulo" id="solicitantes">Quem pode utilizar este serviço?</a><div class="conteudo"><p>Trabalhadores formais
 demitidos sem justa causa.</p></div></li>
 <li><a class="titulo" id="etapas-servico">Etapas</a><div class="conteudo"><ol>
  <li><span>Solicitar</span><div><p>Faça o pedido.</p></div>
   <div class="subtitulo-etapa"><p class="titulo-documento">Canais de prestação</p><div>Web: <a href="https://exemplo.gov.br">Portal</a></div></div>
   <div class="subtitulo-etapa"><p class="titulo-documento">Documentação</p><ul><li><p>- Número do CPF</p></li></ul></div>
   <div class="subtitulo-etapa"><p class="titulo-documento">Tempo de duração da etapa</p><div>Até 5 minuto(s)</div></div>
  </li></ol></div></li>
 <li><a class="titulo" id="outras">Outras Informações</a><div class="conteudo">
  <div><b class="titulo_outros">Quanto tempo leva?</b><div><span>Entre</span> <span>31</span> <span>e</span> <span>60</span> dias</div></div>
  <div><span>Este serviço é gratuito para o cidadão.</span></div>
 </div></li>
</ul></div></body></html>"""

API_OK = {"hasErro": False, "resposta": {
    "nome": "Solicitar o Seguro-Desemprego",
    "descricao": "O Seguro-Desemprego garante assistência financeira temporária ao trabalhador dispensado sem justa causa.",
    "gratuito": "true",
    "contato": "Telefone 158",
    "solicitantes": {"solicitante": [{"tipo": "Trabalhadores formais", "requisitos": "a) sem renda própria"}]},
    "tempoTotalEstimado": {"entre": {"min": "31", "max": "60", "unidade": "dias-corridos"}},
    "validadeDocumento": {"tipo": "Sem validade"},
    "etapas": [{"titulo": "Solicitar", "descricao": "Peça pelo [Portal](https://exemplo.gov.br) ou app.",
                "documentos": {"documentos": [{"nome": "Requerimento do Seguro-Desemprego"},
                                              {"nome": "Número do CPF"}], "casos": []},
                "canaisDePrestacao": {"canaisDePrestacao": [{"tipo": "web", "descricao": "[Portal de ServiÃ§os](https://exemplo.gov.br)"}],
                                      "casos": []},
                "custos": {"custos": None, "casos": []}}],
    "url": "https://www.gov.br/pt-br/servicos/solicitar-o-seguro-desemprego",
}}


class _Resp:
    def __init__(self, text: str = "", payload: dict | None = None):
        self.text, self._payload, self.encoding, self.apparent_encoding = text, payload, "utf-8", "utf-8"

    def json(self):
        return self._payload


class FakeHttp:
    """Substitui col._Http: responde página e API sem rede; `falhar=True` simula site fora do ar."""
    falhar = False
    chamadas: list[str] = []

    def __init__(self, cfg):
        pass

    def get(self, url):
        FakeHttp.chamadas.append(url)
        if FakeHttp.falhar:
            raise requests.ConnectionError("rede indisponível (simulado)")
        if url.startswith(col.API_BASE):
            return _Resp(payload=API_OK)
        return _Resp(text=HTML_CARTA)

    def close(self):
        pass


class TestParsers(unittest.TestCase):
    def test_parse_api_preenche_secoes(self):
        c = col._parse_api(API_OK["resposta"])
        self.assertEqual(set(c["secoes"]), set(col.SECOES))
        for chave in ("descricao", "requisitos", "documentos", "etapas", "canais", "prazos", "custos"):
            self.assertTrue(c["secoes"][chave], chave)
        self.assertIn("Portal de Serviços (https://exemplo.gov.br)", c["secoes"]["canais"])  # mojibake + link
        self.assertIn("Entre 31 e 60", c["secoes"]["prazos"])

    def test_parse_html_mapeia_secoes(self):
        c = col._parse_html(HTML_CARTA)
        s = c["secoes"]
        self.assertEqual(c["titulo"], "Solicitar o Seguro-Desemprego")
        self.assertIn("CPF", s["documentos"])
        self.assertIn("Portal (https://exemplo.gov.br)", s["canais"])
        self.assertIn("Até 5 minuto(s)", s["prazos"])
        self.assertIn("gratuito", s["custos"])
        self.assertTrue(s["etapas"].startswith("1. Solicitar"))

    def test_html_sem_carta_gera_erro(self):
        with self.assertRaises(col.ParseError):
            col._parse_html("<html><body>Página não encontrada</body></html>")

    def test_api_sem_servico_gera_erro(self):
        with self.assertRaises(col.ParseError):
            col._validar_api({"resposta": None, "hasErro": True, "mensagem": "Não existe"})


class TestUpdateCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.corpus, self.cache = base / "corpus.jsonl", base / "cache"
        FakeHttp.falhar, FakeHttp.chamadas = False, []
        self.patch = mock.patch.object(col, "_Http", FakeHttp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _rodar(self, **kw):
        return col.update_corpus(corpus_path=self.corpus, cache_dir=self.cache, service_ids=[SID], **kw)

    def _registro(self):
        return json.loads(self.corpus.read_text(encoding="utf-8").splitlines()[0])

    def test_coleta_api_e_contrato(self):
        r = self._rodar(offline=False)
        self.assertEqual((r.atualizados, r.inalterados, r.falhas, r.usou_cache), (1, 0, [], []))
        reg = self._registro()
        self.assertEqual(reg["fonte"], "api")
        self.assertTrue(reg["data_coleta"].endswith("-03:00"))
        self.assertEqual(set(reg), {"id", "service_id", "titulo", "orgao", "url", "data_coleta", "fonte",
                                    "content_hash", "secoes", "texto_completo"})
        self.assertTrue((self.cache / f"{SID}.json").exists() and (self.cache / f"{SID}.html").exists())

    def test_idempotencia_mantem_registro_antigo(self):
        self._rodar(offline=False)
        antes = self._registro()
        r = self._rodar(offline=False)
        self.assertEqual((r.atualizados, r.inalterados), (0, 1))
        self.assertEqual(self._registro(), antes)   # inclusive data_coleta

    def test_fallback_cache_quando_rede_falha(self):
        self._rodar(offline=False)
        self.corpus.unlink()                         # força gravar o registro vindo do cache
        FakeHttp.falhar = True
        r = self._rodar(offline=False)
        self.assertEqual(r.usou_cache, [SID])
        self.assertEqual(r.falhas, [])
        self.assertEqual(self._registro()["fonte"], "cache")

    def test_offline_nao_acessa_rede(self):
        self._rodar(offline=False)
        FakeHttp.chamadas = []
        r = self._rodar(offline=True)
        self.assertEqual(FakeHttp.chamadas, [])
        self.assertEqual((r.usou_cache, r.inalterados), ([SID], 1))

    def test_sem_rede_e_sem_cache_registra_falha_sem_quebrar(self):
        FakeHttp.falhar = True
        r = self._rodar(offline=False)
        self.assertEqual(r.falhas, [SID])
        self.assertEqual(self.corpus.read_text(encoding="utf-8"), "")

    def test_api_fora_usa_html(self):
        original = FakeHttp.get

        def get_sem_api(self_, url):
            if url.startswith(col.API_BASE):
                raise col.PermanentHTTPError("HTTP 404")
            return original(self_, url)

        with mock.patch.object(FakeHttp, "get", get_sem_api):
            self._rodar(offline=False)
        self.assertEqual(self._registro()["fonte"], "html")


class TestRetryHttp(unittest.TestCase):
    def test_retry_em_503_e_sem_retry_em_404(self):
        http = col._Http({"timeout_s": 1, "retries": 3, "backoff_s": 0, "delay_s": 0})
        r503, r200, r404 = mock.Mock(status_code=503), mock.Mock(status_code=200), mock.Mock(status_code=404)
        with mock.patch.object(http.session, "get", side_effect=[r503, r200]) as g:
            self.assertIs(http.get("https://x.gov.br"), r200)
            self.assertEqual(g.call_count, 2)
        with mock.patch.object(http.session, "get", return_value=r404) as g:
            with self.assertRaises(col.PermanentHTTPError):
                http.get("https://x.gov.br")
            self.assertEqual(g.call_count, 1)


if __name__ == "__main__":
    unittest.main()
