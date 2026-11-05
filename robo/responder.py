"""Geração da resposta ao cidadão.

Caminho principal: assistente RAG do genAI (Gemini, com citações e abstenção).
Caminho seguro: se o RAG não estiver disponível, falhar, se abstiver ou devolver resposta vazia,
a resposta é montada por template a partir dos dados estruturados da Carta de Serviço.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from .config import load_config, path
from .privacy import mask_pii
from .resilience import get_logger

log = get_logger("responder")
_RAG: Any = None
_RAG_ERROR: str | None = None


@dataclass
class Resposta:
    corpo: str
    fonte: str                 # "rag" | "template"
    citacoes: list[dict] = field(default_factory=list)
    motivo_fallback: str | None = None


def _get_rag() -> Any:
    """Importa o RAGAssistant do genAI uma única vez. Falha de import não derruba o robô."""
    global _RAG, _RAG_ERROR
    if _RAG is not None or _RAG_ERROR is not None:
        return _RAG
    try:
        genai_dir = path("genai_path")
        if str(genai_dir) not in sys.path:
            sys.path.insert(0, str(genai_dir))
        from citizen_rag.rag import RAGAssistant  # type: ignore
        _RAG = RAGAssistant(corpus_path=path("corpus"))
        log.info("Assistente RAG carregado de %s", genai_dir)
    except Exception as exc:  # caminho seguro: segue com template
        _RAG_ERROR = f"{type(exc).__name__}: {exc}"
        log.warning("RAG indisponível, usando template: %s", _RAG_ERROR)
    return _RAG


def _secao(rec: dict | None, nome: str) -> str:
    if not rec:
        return ""
    return (rec.get("secoes") or {}).get(nome, "").strip()


def _resumo(texto: str, limite: int = 900) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0] + "…"


def _bloco_documentos(doc_check: Any, doc_names: dict[str, str]) -> str:
    if doc_check is None:
        return ""
    linhas = []
    if doc_check.presentes:
        linhas.append("Documentos que recebemos: " + ", ".join(doc_names.get(d, d) for d in doc_check.presentes) + ".")
    if doc_check.faltantes:
        linhas.append("ATENÇÃO — ainda faltam: " + ", ".join(doc_names.get(d, d) for d in doc_check.faltantes) + ".")
    else:
        linhas.append("Pelos anexos enviados, você já tem todos os documentos exigidos.")
    if doc_check.ilegiveis:
        linhas.append(f"Não conseguimos ler {len(doc_check.ilegiveis)} anexo(s); envie uma foto mais nítida.")
    return "\n".join(linhas)


def template(service: dict, rec: dict | None, doc_check: Any) -> str:
    cfg = load_config()
    doc_names = cfg["document_types"]
    partes = [f"Serviço identificado: {service['nome']} ({service['orgao']})."]
    bloco = _bloco_documentos(doc_check, doc_names)
    if bloco:
        partes.append(bloco)
    for titulo, chave in [("Quem pode solicitar", "requisitos"), ("Etapas", "etapas"),
                          ("Onde solicitar", "canais"), ("Prazo", "prazos"), ("Custos", "custos")]:
        txt = _secao(rec, chave)
        if txt:
            partes.append(f"{titulo}: {_resumo(txt, 600)}")
    if rec:
        partes.append(f"Fonte oficial: {rec.get('url')} (consultada em {str(rec.get('data_coleta', ''))[:10]}).")
    else:
        partes.append(f"Fonte oficial: {service['url']}.")
    return "\n\n".join(partes)


def gerar_resposta(texto: str, service: dict, rec: dict | None, doc_check: Any) -> Resposta:
    """Tenta o RAG e cai no template em qualquer problema."""
    base = template(service, rec, doc_check)
    if not load_config()["responder"].get("use_genai", True):
        return Resposta(base, "template", motivo_fallback="genai_desativado")
    rag = _get_rag()
    if rag is None:
        return Resposta(base, "template", motivo_fallback="rag_indisponivel")
    try:
        out = rag.answer(mask_pii(texto), service_id=service["id"])  # nunca envia PII ao LLM
    except Exception as exc:
        log.exception("Erro no RAG: %s", exc)
        return Resposta(base, "template", motivo_fallback=f"erro_rag: {exc}")
    answer = (out or {}).get("answer", "") if isinstance(out, dict) else ""
    if not answer.strip() or out.get("abstained") or out.get("blocked"):
        motivo = (out or {}).get("reason") or "resposta_vazia_ou_abstencao"
        log.info("RAG sem resposta utilizável (%s); usando template", motivo)
        return Resposta(base, "template", motivo_fallback=motivo)
    doc_names = load_config()["document_types"]
    bloco = _bloco_documentos(doc_check, doc_names)
    fontes = "\n".join(f"[{c.get('n')}] {c.get('titulo')} — {c.get('url')}" for c in out.get("citations", []))
    corpo = "\n\n".join(p for p in [answer.strip(), bloco, "Fontes:\n" + fontes if fontes else ""] if p)
    return Resposta(corpo, "rag", citacoes=out.get("citations", []))


def resposta_revisao(motivo: str) -> str:
    return ("Recebemos sua solicitação. Ela foi encaminhada para um atendente, que vai responder em breve.\n"
            f"Motivo do encaminhamento: {motivo}.")
