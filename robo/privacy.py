"""Mascaramento de dados pessoais (LGPD) antes de logar, classificar ou enviar texto para a IA.

`mask_pii(text)` troca CPF, e-mail, telefone e RG por marcadores: `[CPF]`, `[EMAIL]`,
`[TELEFONE]`, `[RG]`. As regras são deliberadamente precisas para não mascarar números
comuns (anos, valores em reais, "2 meses", datas, CEP, protocolo).

Ordem de aplicação (importa, porque os formatos se sobrepõem):
1. e-mail;
2. CPF pontuado (000.000.000-00 e variações com espaço);
3. RG com palavra-chave ("RG", "identidade", "registro geral") ou pontuado (12.345.678-9);
4. telefone com separadores ou com DDD entre parênteses / +55;
5. sequência de 11 dígitos sem pontuação: CPF se houver "cpf" logo antes; telefone se tiver
   o formato de celular (DDD + 9); caso contrário CPF (na dúvida, mascara).
"""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# CPF pontuado: 123.456.789-09, 123.456.789 09, 123456789-09
CPF_PONTUADO_RE = re.compile(r"(?<![\d.])\d{3}[.\s]\d{3}[.\s]\d{3}[-\s.]\d{2}(?![\d])|(?<![\d.])\d{9}-\d{2}(?!\d)")

# RG precedido de palavra-chave: "RG: 12.345.678-9", "RG nº MG-12.345.678", "identidade 1234567"
RG_CHAVE_RE = re.compile(
    r"(?i)\b(R\.?G\.?|registro\s+geral|(?:carteira\s+de\s+)?identidade)(\s*(?:n[º°o.]*|numero|número)?\s*[:\-]?\s*)"
    r"((?:[A-Z]{2}[-\s]?)?\d[\d.\-]{3,12}[\dXx])\b"
)
# RG pontuado sem palavra-chave: 12.345.678-9 / 1.234.567-X (não confunde com valores 1.234,56)
RG_PONTUADO_RE = re.compile(r"(?<![\d.])(?:[A-Z]{2}-)?\d{1,2}\.\d{3}\.\d{3}-[\dXx](?![\d])")

# Telefone com DDD: (11) 98765-4321, 11 98765 4321, +55 11 3456-7890, (011) 3456.7890
TEL_DDD_RE = re.compile(
    r"(?<![\w])(?:\+?55[\s-]?)?(?:\(0?\d{2}\)\s?|0?\d{2}[\s-])9?\d{4}[\s.-]?\d{4}(?![\d])"
)
# Telefone sem DDD, exige hífen: 98765-4321 / 3456-7890 (evita "2025-2026" e outros pares de anos)
TEL_LOCAL_RE = re.compile(r"(?<![\d.\-/])(?!(?:19|20)\d{2}-(?:19|20)\d{2}\b)(?:9\d{4}|[2-5]\d{3})-\d{4}(?![\d\-/])")
# +55 seguido de dígitos colados: +5511987654321
TEL_INTL_RE = re.compile(r"\+55\s?\d{10,11}(?!\d)")
# Telefone precedido de palavra-chave, mesmo só com espaço: "tel: 3456 7890", "whatsapp 98765 4321"
TEL_CHAVE_RE = re.compile(
    r"(?i)\b(tel(?:efone)?|cel(?:ular)?|fone|whats(?:app)?|zap)(\.?\s*[:\-]?\s*)(\d{4,5}[\s.]?\d{4})(?![\d])"
)

ONZE_DIGITOS_RE = re.compile(r"(?<![\d.\-/])\d{11}(?![\d.\-/])")
CELULAR_RE = re.compile(r"^[1-9][1-9]9\d{8}$")


def _onze_digitos(match: re.Match, text: str) -> str:
    numero = match.group(0)
    antes = text[max(0, match.start() - 20):match.start()].lower()
    if "cpf" in antes:
        return "[CPF]"
    if any(k in antes for k in ("tel", "cel", "fone", "whats", "zap", "contato")):
        return "[TELEFONE]"
    if CELULAR_RE.match(numero):
        return "[TELEFONE]"
    return "[CPF]"


def mask_pii(text: str) -> str:
    """Substitui dados pessoais por marcadores. Nunca lança exceção (texto inválido -> "")."""
    if not text:
        return "" if text is None else text
    if not isinstance(text, str):
        text = str(text)
    out = EMAIL_RE.sub("[EMAIL]", text)
    out = CPF_PONTUADO_RE.sub("[CPF]", out)
    out = RG_CHAVE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[RG]", out)
    out = RG_PONTUADO_RE.sub("[RG]", out)
    out = TEL_INTL_RE.sub("[TELEFONE]", out)
    out = TEL_DDD_RE.sub("[TELEFONE]", out)
    out = TEL_CHAVE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[TELEFONE]", out)
    out = TEL_LOCAL_RE.sub("[TELEFONE]", out)
    out = ONZE_DIGITOS_RE.sub(lambda m: _onze_digitos(m, out), out)
    return out


__all__ = ["mask_pii"]
