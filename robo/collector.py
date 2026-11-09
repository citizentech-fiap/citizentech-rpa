"""Coletor das Cartas de Serviço do gov.br -> corpus JSONL usado pelo RAG.

Fonte principal: API pública do Portal de Serviços (https://www.servicos.gov.br/api/v1/servicos/{id}),
que devolve a Carta de Serviço estruturada (etapas, documentos, canais, custos, prazos).
O id numérico do serviço é lido da própria página da carta (<meta name="identificador">), o que
também confirma que a URL do config.yaml continua válida.

Caminhos de contingência (nunca derrubam a execução inteira):
  1. API falhou ou o serviço não está na API  -> raspagem do HTML da página (fonte="html");
  2. rede indisponível / página quebrada / collector.offline=true -> cópia bruta salva em cache
     (fonte="cache", registrado em usou_cache);
  3. sem cache -> erro no log, serviço vai para `falhas` e o registro anterior do corpus (se houver)
     é preservado.

Idempotência: o content_hash (sha256 do texto_completo) é comparado com o registro já existente no
corpus; se for igual, o registro antigo é mantido intacto (inclusive data_coleta) e conta como inalterado.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from robo.config import load_config, path, services
from robo.resilience import get_logger, retry

log = get_logger("collector")

API_BASE = "https://www.servicos.gov.br/api/v1/servicos/"
TZ_BR = timezone(timedelta(hours=-3))
SECOES = ("descricao", "requisitos", "documentos", "etapas", "canais", "prazos", "custos")
ROTULOS = {
    "descricao": "O que é?",
    "requisitos": "Quem pode utilizar este serviço / requisitos",
    "documentos": "Documentos necessários",
    "etapas": "Etapas para a realização do serviço",
    "canais": "Canais de atendimento",
    "prazos": "Prazos e tempo estimado",
    "custos": "Custos",
}
MIN_TEXTO = 200          # abaixo disso a página é considerada quebrada/incompleta
DELAY_PADRAO_S = 1.0     # intervalo educado entre requisições (collector.delay_s, se existir)


# --------------------------------------------------------------------------------------------
# Tipos
# --------------------------------------------------------------------------------------------
@dataclass
class CollectResult:
    atualizados: int = 0
    inalterados: int = 0
    falhas: list[str] = field(default_factory=list)
    usou_cache: list[str] = field(default_factory=list)
    fontes: dict[str, str] = field(default_factory=dict)   # service_id -> fonte do conteúdo desta execução

    def resumo(self) -> str:
        return (f"atualizados={self.atualizados} inalterados={self.inalterados} "
                f"falhas={self.falhas} usou_cache={self.usou_cache}")


class TransientHTTPError(Exception):
    """HTTP 429/5xx: vale tentar de novo (retry com espera exponencial)."""


class PermanentHTTPError(Exception):
    """HTTP 4xx (404, 403...): repetir não resolve; vai direto para o caminho de contingência."""


class ParseError(Exception):
    """Conteúdo baixado não tem a estrutura esperada de uma Carta de Serviço."""


ERROS_TRANSITORIOS = (requests.ConnectionError, requests.Timeout,
                      requests.exceptions.ChunkedEncodingError, TransientHTTPError)


# --------------------------------------------------------------------------------------------
# HTTP educado + retry
# --------------------------------------------------------------------------------------------
class _Http:
    def __init__(self, cfg: dict[str, Any]):
        self.timeout = float(cfg.get("timeout_s", 15))
        self.delay = float(cfg.get("delay_s", DELAY_PADRAO_S))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": cfg.get("user_agent", "CitizenTechBot/1.0"),
            "Accept-Language": "pt-BR,pt;q=0.9",
        })
        self._ultimo = 0.0
        self.get = retry(times=int(cfg.get("retries", 3)), backoff_s=float(cfg.get("backoff_s", 2)),
                         exceptions=ERROS_TRANSITORIOS, logger=log)(self._get_uma_vez)

    def _get_uma_vez(self, url: str) -> requests.Response:
        espera = self.delay - (time.monotonic() - self._ultimo)
        if espera > 0:
            time.sleep(espera)
        try:
            resp = self.session.get(url, timeout=self.timeout)
        finally:
            self._ultimo = time.monotonic()
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientHTTPError(f"HTTP {resp.status_code} em {url}")
        if resp.status_code >= 400:
            raise PermanentHTTPError(f"HTTP {resp.status_code} em {url}")
        return resp

    def close(self) -> None:
        self.session.close()


# --------------------------------------------------------------------------------------------
# Limpeza de texto
# --------------------------------------------------------------------------------------------
_ZW = re.compile(r"[​‌‍⁠﻿]")
_CMS_LIXO = re.compile(r"ATEN[ÇC][ÃA]O EDITOR|edite DIRETAMENTE no c[óo]digo fonte", re.I)
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _corrigir_mojibake(s: str) -> str:
    """Alguns campos da API vêm com UTF-8 lido como Latin-1 ('ServiÃ§os'); tenta desfazer."""
    if "Ã" not in s and "Â" not in s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _limpar(s: str | None) -> str:
    """Normaliza texto (markdown da API ou texto do HTML) em linhas limpas."""
    if not s:
        return ""
    s = _corrigir_mojibake(_ZW.sub("", str(s))).replace("\xa0", " ").replace("\r", "")

    def _link(m: re.Match) -> str:
        texto, url = m.group(1).strip(), m.group(2).strip()
        if not url.startswith("http"):
            return texto
        if not texto or texto == url:
            return url
        return f"{texto} ({url})"

    s = _MD_LINK.sub(_link, s)
    s = s.replace("**", "").replace("__", "")
    linhas = []
    for ln in s.split("\n"):
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        ln = re.sub(r"^[*•·]\s+", "- ", ln)          # marcadores de lista -> "- "
        if _CMS_LIXO.search(ln):                      # notas internas do CMS do gov.br para editores
            continue
        if ln and ln not in ("-", "*"):
            linhas.append(ln)
    return "\n".join(linhas)


def _juntar(*partes: str) -> str:
    vistos, saida = set(), []
    for p in partes:
        p = (p or "").strip()
        if p and p not in vistos:
            vistos.add(p)
            saida.append(p)
    return "\n".join(saida)


# --------------------------------------------------------------------------------------------
# Parser da API (JSON)
# --------------------------------------------------------------------------------------------
_CANAIS = {"web": "Web", "web-consultar": "Web (consultar)", "web-acompanhar": "Web (acompanhar)",
           "web-agendar": "Web (agendar)", "web-calcular-taxas": "Web (calcular taxas)",
           "web-declarar": "Web (declarar)", "web-inscrever-se": "Web (inscrever-se)",
           "web-emitir": "Web (emitir)", "web-preencher": "Web (preencher)",
           "aplicativo-movel": "Aplicativo móvel", "presencial": "Presencial", "telefone": "Telefone",
           "e-mail": "E-mail", "postal": "Postal", "sms": "SMS", "fax": "Fax"}


def _nome_canal(tipo: str | None) -> str:
    t = (tipo or "canal").strip()
    return _CANAIS.get(t.lower(), t.replace("-", " ").capitalize())


_UNIDADES = {"dias-corridos": "dia(s) corrido(s)", "dias-uteis": "dia(s) útil(eis)",
             "minutos": "minuto(s)", "horas": "hora(s)", "meses": "mês(es)", "anos": "ano(s)",
             "semanas": "semana(s)"}


def _formatar_tempo(t: dict | None) -> str:
    if not t:
        return ""
    un = lambda d: _UNIDADES.get((d or {}).get("unidade") or "", (d or {}).get("unidade") or "")  # noqa: E731
    if t.get("entre"):
        e = t["entre"]
        txt = f"Entre {e.get('min')} e {e.get('max')} {un(e)}"
    elif t.get("ate"):
        txt = f"Até {t['ate'].get('max')} {un(t['ate'])}"
    elif t.get("emMedia"):
        txt = f"Em média {t['emMedia'].get('max')} {un(t['emMedia'])}"
    elif t.get("atendimentoImediato") is not None:
        txt = "Atendimento imediato"
    elif t.get("naoEstimadoAinda") is not None:
        txt = "Não estimado ainda"
    else:
        txt = ""
    return _juntar(txt, _limpar(t.get("descricao")))


def _lista(itens: list[str], prefixo: str = "- ") -> str:
    return "\n".join(prefixo + i.replace("\n", "\n  ") for i in itens if i)


def _parse_api(dados: dict[str, Any]) -> dict[str, Any]:
    etapas = dados.get("etapas") or []
    multi = len(etapas) > 1
    sec = dict.fromkeys(SECOES, "")

    # descricao
    populares = [i.get("item", "") for i in (dados.get("nomesPopulares") or {}).get("item") or []]
    sec["descricao"] = _juntar(_limpar(dados.get("descricao")),
                               ("Também conhecido como: " + ", ".join(populares)) if populares else "")

    # requisitos (quem pode utilizar)
    reqs = []
    for s in (dados.get("solicitantes") or {}).get("solicitante") or []:
        reqs.append(_juntar(_limpar(s.get("tipo")), _limpar(s.get("requisitos"))))
    sec["requisitos"] = _lista(reqs)

    docs, passos, canais, custos = [], [], [], []
    for n, et in enumerate(etapas, 1):
        titulo = _limpar(et.get("titulo")) or f"Etapa {n}"
        passos.append(f"{n}. {_juntar(titulo, _limpar(et.get('descricao')))}")
        cab = f"[{titulo}] " if multi else ""

        d = et.get("documentos") or {}
        itens = [_limpar(x.get("nome") or x.get("descricao")) for x in d.get("documentos") or []]
        if itens:
            docs.append(cab + "Documentação em comum para todos os casos:\n" + _lista(itens))
        for caso in d.get("casos") or []:
            itens = [_limpar(x.get("descricao") or x.get("nome")) for x in caso.get("documento") or []]
            if itens:
                docs.append(f"{cab}Caso: {_limpar(caso.get('descricao'))}\n" + _lista(itens))

        c = et.get("canaisDePrestacao") or {}
        for x in c.get("canaisDePrestacao") or []:
            canais.append(f"{_nome_canal(x.get('tipo'))}: {_limpar(x.get('descricao'))}")
        for caso in c.get("casos") or []:
            for x in caso.get("canalDePrestacao") or []:
                canais.append(f"{_nome_canal(x.get('tipo'))} ({_limpar(caso.get('descricao')).rstrip(':')}): "
                              f"{_limpar(x.get('descricao'))}")

        k = et.get("custos") or {}
        for x in k.get("custos") or []:
            custos.append(f"{cab}{_limpar(x.get('descricao'))}: {x.get('moeda') or 'R$'} "
                          f"{(x.get('valor') or x.get('valorVariavel') or '').strip()}")
        for caso in k.get("casos") or []:
            for x in caso.get("custo") or []:
                custos.append(f"{cab}{_limpar(caso.get('descricao'))} - {_limpar(x.get('descricao'))}: "
                              f"{x.get('moeda') or 'R$'} {(x.get('valor') or x.get('valorVariavel') or '').strip()}")

    sec["documentos"] = "\n\n".join(docs)
    sec["etapas"] = "\n".join(passos)

    if dados.get("linkServicoDigital"):
        canais.append(f"Serviço digital: {dados['linkServicoDigital']}")
    if dados.get("contato"):
        canais.append("Contato: " + _limpar(dados["contato"]))
    sec["canais"] = _lista(list(dict.fromkeys(canais)))

    prazo = _formatar_tempo(dados.get("tempoTotalEstimado"))
    val = dados.get("validadeDocumento") or {}
    validade = ""
    if val.get("tipo") and val.get("tipo") != "Sem validade":
        validade = _juntar(f"Validade do documento: {val.get('tipo')} "
                           f"{val.get('quantidade') or ''} {val.get('unidade') or ''}".strip(),
                           _limpar(val.get("descricao")))
    elif _limpar(val.get("descricao")):
        validade = "Validade do documento: " + _limpar(val.get("descricao"))
    sec["prazos"] = _juntar(("Tempo estimado: " + prazo) if prazo else "", validade)

    gratuito = str(dados.get("gratuito", "")).lower() == "true"
    sec["custos"] = _juntar("Este serviço é gratuito para o cidadão." if gratuito and not custos else
                            ("Serviço com custo para o cidadão." if not gratuito else ""),
                            _lista(custos))

    return {"titulo": _limpar(dados.get("nome")), "secoes": sec, "url_oficial": dados.get("url")}


# --------------------------------------------------------------------------------------------
# Parser do HTML (raspagem da página da carta)
# --------------------------------------------------------------------------------------------
def _texto_el(el: Tag | None) -> str:
    """Texto de um elemento preservando quebras de parágrafo/lista e o destino dos links."""
    if el is None:
        return ""
    el = copy.copy(el)
    for t in el.find_all(["script", "style", "i"]):
        t.decompose()
    for a in el.find_all("a"):
        href, txt = (a.get("href") or "").strip(), a.get_text(" ", strip=True)
        if href.startswith("http") and href not in txt:
            a.replace_with(f"{txt} ({href})" if txt else href)
    # quebras de linha do código-fonte não são quebras de texto: colapsa e recria só nos blocos
    for no in list(el.find_all(string=True)):
        if isinstance(no, NavigableString) and not isinstance(no, Comment):
            no.replace_with(re.sub(r"\s+", " ", str(no)))
        elif isinstance(no, Comment):
            no.extract()
    for br in el.find_all("br"):
        br.replace_with("\n")
    for blk in el.find_all(["p", "li", "div", "tr", "b", "h3", "h4"]):
        blk.insert_before("\n")
        blk.insert_after("\n")
    return _limpar(el.get_text(""))


_MAPA_TITULOS = [  # fallback por palavra-chave no título da seção
    ("descricao", ("o que é",)),
    ("requisitos", ("quem pode", "requisito")),
    ("documentos", ("documento", "documentação")),
    ("etapas", ("etapa", "passo")),
    ("canais", ("canal", "canais", "onde", "contato")),
    ("prazos", ("tempo", "prazo", "validade")),
    ("custos", ("custo", "taxa", "gratuito", "valor")),
]


def _secao_por_titulo(titulo: str) -> str | None:
    t = titulo.lower()
    for chave, palavras in _MAPA_TITULOS:
        if any(p in t for p in palavras):
            return chave
    return None


def _secao_da_subetapa(rotulo: str) -> str | None:
    """Subtítulos dentro de cada etapa ('Documentação', 'Canais de prestação', 'Tempo de duração da etapa'...)."""
    r = rotulo.lower()
    if "document" in r:
        return "documentos"
    if "canal" in r or "canais" in r:
        return "canais"
    if "tempo" in r or "duração" in r or "prazo" in r:
        return "prazos"
    if "custo" in r or "taxa" in r:
        return "custos"
    return None


def _parse_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    ul = soup.select_one("div.servico-content ul.servico") or soup.select_one("ul.servico")
    if ul is None:
        raise ParseError("página sem a estrutura de Carta de Serviço (ul.servico)")

    titulo_el = soup.select_one("div.visao-servico div.titulo") or soup.select_one("div.titulo")
    titulo = ""
    if titulo_el is not None:
        t = copy.copy(titulo_el)
        for sp in t.select("span.nomes-populares"):
            sp.decompose()
        titulo = re.sub(r"\s+", " ", t.get_text(" ")).strip()
    if not titulo:
        h1 = soup.find("h1")
        titulo = h1.get_text(" ", strip=True) if h1 else ""

    partes: dict[str, list[str]] = {k: [] for k in SECOES}
    for li in ul.find_all("li", recursive=False):
        a = li.find("a", class_="titulo")
        cont = li.find("div", class_="conteudo")
        if a is None or cont is None:
            continue
        sid, cab = a.get("id", ""), a.get_text(" ", strip=True)

        if sid == "dados_basicos":
            partes["descricao"].append(_texto_el(cont))
        elif sid == "solicitantes":
            partes["requisitos"].append(_texto_el(cont))
        elif sid == "etapas-servico":
            ol = cont.find("ol")
            etapas_li = ol.find_all("li", recursive=False) if ol else []
            for n, et in enumerate(etapas_li, 1):
                corpo = copy.copy(et)
                nome_et = ""
                sp = corpo.find("span", recursive=False)
                if sp is not None:
                    nome_et = sp.get_text(" ", strip=True)
                    sp.decompose()
                for sub in et.find_all("div", class_="subtitulo-etapa"):
                    sub_c = copy.copy(sub)
                    rot_el = sub_c.find("p", class_="titulo-documento")
                    rot = rot_el.get_text(" ", strip=True) if rot_el else ""
                    if rot_el is not None:
                        rot_el.decompose()
                    alvo = _secao_da_subetapa(rot)
                    conteudo = _texto_el(sub_c)
                    if alvo in ("documentos", "canais", "custos", "prazos") and conteudo:
                        if alvo == "prazos":
                            conteudo = f"Etapa {n} ({nome_et}): {conteudo}"
                        elif len(etapas_li) > 1:
                            conteudo = f"[{nome_et}]\n{conteudo}"
                        partes[alvo].append(conteudo)
                for sub in corpo.find_all("div", class_="subtitulo-etapa"):
                    sub.decompose()
                partes["etapas"].append(f"{n}. {_juntar(nome_et, _texto_el(corpo))}")
        elif sid == "outras":
            for bloco in cont.find_all("div", recursive=False):
                b = bloco.find("b", class_="titulo_outros")
                rot = b.get_text(" ", strip=True) if b else ""
                txt = _texto_el(bloco)
                if not txt:
                    continue
                rl = rot.lower()
                if "quanto tempo" in rl or "tempo estimado" in rl or "validade" in rl:
                    corpo_txt = txt.replace(rot, "", 1).strip()
                    if corpo_txt:
                        partes["prazos"].append(f"{rot}\n{corpo_txt}" if "adiciona" in rl or "validade" in rl
                                                else "Tempo estimado: " + re.sub(r"\s*\n\s*", " ", corpo_txt))
                elif "gratuito" in txt.lower() and not rot:
                    partes["custos"].append(txt)
                elif "contato" in rl:
                    partes["canais"].append("Contato: " + txt.replace(rot, "", 1).strip())
            # página estadual não usa os divs acima: aproveita parágrafos soltos com links/contato
            if not partes["canais"]:
                extra = [_texto_el(p) for p in cont.find_all("p", recursive=False)]
                partes["canais"].extend(x for x in extra if x)
        else:
            alvo = _secao_por_titulo(cab)
            if alvo:
                partes[alvo].append(_texto_el(cont))

    sec = {k: "\n\n".join(x for x in v if x).strip() for k, v in partes.items()}
    return {"titulo": titulo, "secoes": sec, "url_oficial": None}


def _identificador(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", attrs={"name": "identificador"})
    val = (meta.get("content") or "").strip() if meta else ""
    return val if val.isdigit() else None


# --------------------------------------------------------------------------------------------
# Cache bruto por serviço (output/cache_html/<service_id>.{html,json,meta.json})
# --------------------------------------------------------------------------------------------
def _escrever_atomico(destino: Path, conteudo: str) -> None:
    if destino.exists() and destino.read_text(encoding="utf-8") == conteudo:
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_text(conteudo, encoding="utf-8")
    os.replace(tmp, destino)


class _Cache:
    def __init__(self, pasta: Path):
        self.pasta = pasta
        self.pasta.mkdir(parents=True, exist_ok=True)

    def _p(self, sid: str, ext: str) -> Path:
        return self.pasta / f"{sid}.{ext}"

    def salvar(self, sid: str, url: str, html: str, api_json: Any | None, formato: str,
               api_id: str | None, data_coleta: str) -> None:
        anteriores = {ext: self._p(sid, ext).read_text(encoding="utf-8")
                      for ext in ("html", "json") if self._p(sid, ext).exists()}
        _escrever_atomico(self._p(sid, "html"), html)
        if api_json is not None:
            _escrever_atomico(self._p(sid, "json"), json.dumps(api_json, ensure_ascii=False, indent=1))
        meta = {"service_id": sid, "url": url, "formato": formato, "api_id": api_id,
                "data_coleta": data_coleta}
        meta_path = self._p(sid, "meta.json")
        if meta_path.exists():
            try:
                antiga = json.loads(meta_path.read_text(encoding="utf-8"))
                iguais = anteriores.get("html") == html and (api_json is None or
                    anteriores.get("json") == json.dumps(api_json, ensure_ascii=False, indent=1))
                if iguais and all(antiga.get(k) == meta[k] for k in meta if k != "data_coleta"):
                    meta["data_coleta"] = antiga["data_coleta"]
            except (ValueError, KeyError):
                pass
        _escrever_atomico(self._p(sid, "meta.json"), json.dumps(meta, ensure_ascii=False, indent=1))

    def carregar(self, sid: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Devolve (conteudo_parseado, meta). Lança FileNotFoundError se não houver cache utilizável."""
        meta: dict[str, Any] = {}
        if self._p(sid, "meta.json").exists():
            try:
                meta = json.loads(self._p(sid, "meta.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("[%s] meta do cache ilegível (%s); tentando arquivos brutos", sid, exc)
        tentativas = (["json", "html"] if meta.get("formato", "api") == "api" else ["html", "json"])
        erros = []
        for ext in tentativas:
            arq = self._p(sid, ext)
            if not arq.exists():
                continue
            try:
                bruto = arq.read_text(encoding="utf-8")
                if ext == "json":
                    conteudo = _parse_api(_validar_api(json.loads(bruto)))
                else:
                    conteudo = _parse_html(bruto)
                _validar_conteudo(conteudo)
                meta.setdefault("formato", "api" if ext == "json" else "html")
                return conteudo, meta
            except Exception as exc:  # cache corrompido: tenta o outro formato
                erros.append(f"{arq.name}: {type(exc).__name__}: {exc}")
        raise FileNotFoundError(f"sem cache utilizável para {sid}" + (f" ({'; '.join(erros)})" if erros else ""))

    def api_id(self, sid: str) -> str | None:
        try:
            return json.loads(self._p(sid, "meta.json").read_text(encoding="utf-8")).get("api_id")
        except (OSError, json.JSONDecodeError):
            return None


# --------------------------------------------------------------------------------------------
# Coleta de um serviço
# --------------------------------------------------------------------------------------------
def _validar_api(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("hasErro") or not isinstance(payload.get("resposta"), dict):
        msg = payload.get("mensagem") if isinstance(payload, dict) else "resposta inesperada"
        raise ParseError(f"API sem o serviço: {msg}")
    return payload["resposta"]


def _validar_conteudo(conteudo: dict[str, Any]) -> None:
    total = sum(len(v) for v in conteudo["secoes"].values())
    if total < MIN_TEXTO or not conteudo["secoes"].get("descricao"):
        raise ParseError(f"conteúdo insuficiente ({total} caracteres nas seções)")


def _agora() -> str:
    return datetime.now(TZ_BR).isoformat(timespec="seconds")


def _coletar_online(svc: dict[str, Any], http: _Http, cache: _Cache) -> tuple[dict[str, Any], str, str]:
    """Baixa a página (+ API quando houver id) e devolve (conteudo, fonte, data_coleta)."""
    sid, url = svc["id"], svc["url"]
    html, api_id = None, None
    try:
        resp = http.get(url)
        resp.encoding = resp.encoding or resp.apparent_encoding
        html = resp.text
        api_id = _identificador(html)
    except Exception as exc:
        # página fora do ar: se já conhecemos o id da API, ainda dá para buscar a carta estruturada
        api_id = cache.api_id(sid)
        if not api_id:
            raise
        log.warning("[%s] página indisponível (%s); tentando a API direto (id %s)", sid, exc, api_id)

    if api_id:
        try:
            payload = http.get(API_BASE + api_id).json()
            conteudo = _parse_api(_validar_api(payload))
            _validar_conteudo(conteudo)
            oficial = conteudo.get("url_oficial")
            if oficial and oficial.rstrip("/") != url.rstrip("/"):
                log.warning("[%s] URL do config difere da URL oficial da API: %s", sid, oficial)
            data = _agora()
            cache.salvar(sid, url, html if html is not None else "", payload, "api", api_id, data)
            return conteudo, "api", data
        except Exception as exc:
            if html is None:
                raise
            log.warning("[%s] API falhou (%s: %s); usando raspagem do HTML", sid, type(exc).__name__, exc)

    conteudo = _parse_html(html)
    _validar_conteudo(conteudo)
    data = _agora()
    cache.salvar(sid, url, html, None, "html", api_id, data)
    return conteudo, "html", data


def _montar_registro(svc: dict[str, Any], conteudo: dict[str, Any], fonte: str, data_coleta: str) -> dict[str, Any]:
    titulo = conteudo.get("titulo") or svc.get("nome") or svc["id"]
    orgao = svc.get("orgao", "")
    secoes = {k: (conteudo["secoes"].get(k) or "").strip() for k in SECOES}
    blocos = [titulo, f"Órgão responsável: {orgao}" if orgao else ""]
    blocos += [f"{ROTULOS[k]}\n{secoes[k]}" for k in SECOES if secoes[k]]
    texto = "\n\n".join(b for b in blocos if b)
    return {
        "id": svc["id"],
        "service_id": svc["id"],
        "titulo": titulo,
        "orgao": orgao,
        "url": svc["url"],
        "data_coleta": data_coleta,
        "fonte": fonte,
        "content_hash": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        "secoes": secoes,
        "texto_completo": texto,
    }


# --------------------------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------------------------
def _ler_corpus(arquivo: Path) -> dict[str, dict[str, Any]]:
    registros: dict[str, dict[str, Any]] = {}
    if not arquivo.exists():
        return registros
    with open(arquivo, encoding="utf-8") as fh:
        for n, linha in enumerate(fh, 1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                reg = json.loads(linha)
                registros[reg["service_id"]] = reg
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                log.warning("Linha %d do corpus ignorada (inválida): %s", n, exc)
    return registros


def _gravar_corpus(arquivo: Path, registros: list[dict[str, Any]]) -> None:
    _escrever_atomico(arquivo, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros))


def update_corpus(offline: bool | None = None, corpus_path: str | Path | None = None,
                  cache_dir: str | Path | None = None, service_ids: list[str] | None = None) -> CollectResult:
    """Atualiza o corpus JSONL com as Cartas de Serviço de todos os serviços do config.

    offline=None usa collector.offline do config; True força o uso exclusivo do cache.
    corpus_path/cache_dir/service_ids permitem testes sem mexer nos arquivos oficiais.
    """
    cfg = load_config().get("collector", {}) or {}
    offline = bool(cfg.get("offline", False)) if offline is None else offline
    arquivo = Path(corpus_path) if corpus_path else path("corpus")
    cache = _Cache(Path(cache_dir) if cache_dir else path("corpus_cache_dir"))
    catalogo = [s for s in services() if not service_ids or s["id"] in service_ids]

    antigos = _ler_corpus(arquivo)
    resultado = CollectResult()
    novos: list[dict[str, Any]] = []
    http = None if offline else _Http(cfg)
    log.info("Coleta iniciada: %d serviço(s), modo %s", len(catalogo), "OFFLINE (cache)" if offline else "online")

    try:
        for svc in catalogo:
            sid = svc["id"]
            try:
                conteudo = fonte = data = None
                if not offline:
                    try:
                        conteudo, fonte, data = _coletar_online(svc, http, cache)
                    except Exception as exc:
                        log.warning("[%s] coleta online falhou (%s: %s); recorrendo ao cache",
                                    sid, type(exc).__name__, exc)
                if conteudo is None:
                    conteudo, meta = cache.carregar(sid)
                    fonte, data = "cache", meta.get("data_coleta") or _agora()
                    resultado.usou_cache.append(sid)
                    log.info("[%s] usando cópia em cache (coletada em %s)", sid, data)

                reg = _montar_registro(svc, conteudo, fonte, data)
                antigo = antigos.get(sid)
                resultado.fontes[sid] = fonte
                if antigo and antigo.get("content_hash") == reg["content_hash"]:
                    novos.append(antigo)
                    resultado.inalterados += 1
                    log.info("[%s] inalterado (hash %s…)", sid, reg["content_hash"][:12])
                else:
                    novos.append(reg)
                    resultado.atualizados += 1
                    log.info("[%s] %s via %s (%d caracteres)", sid, "atualizado" if antigo else "incluído",
                             fonte, len(reg["texto_completo"]))
            except Exception as exc:  # sem rede e sem cache: registra e segue para o próximo
                resultado.falhas.append(sid)
                log.error("[%s] serviço não coletado: %s: %s", sid, type(exc).__name__, exc)
                if sid in antigos:
                    novos.append(antigos[sid])
                    log.warning("[%s] mantido o registro anterior do corpus", sid)
    finally:
        if http is not None:
            http.close()

    # serviços fora do filtro service_ids continuam no corpus
    if service_ids:
        ids_novos = {r["service_id"] for r in novos}
        ordem = [s["id"] for s in services()]
        novos += [r for k, r in antigos.items() if k not in ids_novos]
        novos.sort(key=lambda r: ordem.index(r["service_id"]) if r["service_id"] in ordem else len(ordem))

    try:
        _gravar_corpus(arquivo, novos)
    except OSError as exc:
        log.error("Não foi possível gravar o corpus em %s: %s", arquivo, exc)
        resultado.falhas.append("__gravacao_corpus__")
    log.info("Coleta concluída: %s", resultado.resumo())
    return resultado


if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")  # console do Windows
    ap = argparse.ArgumentParser(description="Atualiza o corpus de Cartas de Serviço do gov.br")
    ap.add_argument("--offline", action="store_true", help="não acessa a rede; usa só o cache")
    args = ap.parse_args()
    res = update_corpus(offline=True if args.offline else None)
    print(json.dumps(asdict(res), ensure_ascii=False, indent=2))
