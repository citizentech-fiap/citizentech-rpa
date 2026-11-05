"""Leitura e validação das solicitações da caixa de entrada (`inbox/*.json`).

Regras de validação (ver CONTRACTS.md):
- JSON que não abre (sintaxe quebrada, encoding inválido, não é objeto) -> InvalidItem;
- `request_id` ausente/vazio ou `texto` ausente/vazio -> InvalidItem;
- `request_id` repetido em outro arquivo -> InvalidItem (o primeiro vale);
- `anexos` que não é lista -> InvalidItem.

Decisão de projeto sobre anexos inexistentes: a solicitação continua VÁLIDA. O caminho que não
existe (ou que aponta para fora da pasta da inbox, por segurança) vai para o campo extra
`anexos_ausentes` (lista com os caminhos como vieram no JSON) e não entra em `anexos_abs`.
Assim o robô ainda consegue classificar o pedido e cabe ao orquestrador decidir o desfecho
(ex.: tratar como inválido quando nenhum anexo informado existe, ou pedir o reenvio).

Toda rejeição é registrada no log. `load_requests` nunca lança exceção.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .resilience import get_logger

log = get_logger("inbox")


@dataclass
class Request:
    request_id: str
    texto: str
    data_envio: str | None = None
    nome: str | None = None
    email: str | None = None
    cpf: str | None = None
    anexos: list[str] = field(default_factory=list)
    source_path: Path | None = None
    anexos_abs: list[Path] = field(default_factory=list)
    # Extensão documentada: anexos citados no JSON que não existem no disco.
    anexos_ausentes: list[str] = field(default_factory=list)
    municipio: str = ""
    uf: str = ""
    cod_ibge: str = ""


@dataclass
class InvalidItem:
    source_path: Path
    reason: str


def _texto_opcional(valor: Any) -> str | None:
    if valor is None:
        return None
    return str(valor).strip() or None


def _resolver_anexo(inbox_dir: Path, rel: str) -> Path | None:
    """Resolve o caminho do anexo relativo à inbox. Devolve None se não existir ou sair da inbox."""
    try:
        p = Path(rel)
        cand = (p if p.is_absolute() else inbox_dir / p).resolve()
        cand.relative_to(inbox_dir)  # bloqueia "../../arquivo" fora da inbox
    except (ValueError, OSError):
        return None
    return cand if cand.is_file() else None


def _validar(arquivo: Path, inbox_dir: Path, vistos: set[str]) -> Request | InvalidItem:
    try:
        bruto = arquivo.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return InvalidItem(arquivo, f"arquivo ilegível: {type(exc).__name__}: {exc}")
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        return InvalidItem(arquivo, f"JSON malformado (linha {exc.lineno}, coluna {exc.colno}): {exc.msg}")
    if not isinstance(dados, dict):
        return InvalidItem(arquivo, "JSON não é um objeto")

    request_id = _texto_opcional(dados.get("request_id"))
    if not request_id:
        return InvalidItem(arquivo, "campo obrigatório ausente ou vazio: request_id")
    texto = dados.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        return InvalidItem(arquivo, f"campo obrigatório ausente ou vazio: texto ({request_id})")
    if request_id in vistos:
        return InvalidItem(arquivo, f"request_id duplicado: {request_id}")

    anexos = dados.get("anexos", []) or []
    if not isinstance(anexos, list) or not all(isinstance(a, str) for a in anexos):
        return InvalidItem(arquivo, f"campo anexos deve ser lista de caminhos ({request_id})")

    anexos_abs: list[Path] = []
    ausentes: list[str] = []
    for rel in anexos:
        p = _resolver_anexo(inbox_dir, rel)
        if p is None:
            ausentes.append(rel)
        else:
            anexos_abs.append(p)
    if ausentes:
        log.warning("%s: anexo(s) não encontrado(s) ou fora da inbox: %s", request_id, ", ".join(ausentes))

    vistos.add(request_id)
    return Request(
        request_id=request_id,
        texto=texto.strip(),
        data_envio=_texto_opcional(dados.get("data_envio")),
        nome=_texto_opcional(dados.get("nome")),
        email=_texto_opcional(dados.get("email")),
        cpf=_texto_opcional(dados.get("cpf")),
        municipio=_texto_opcional(dados.get("municipio")) or "",
        uf=_texto_opcional(dados.get("uf")) or "",
        cod_ibge=_texto_opcional(dados.get("cod_ibge")) or "",
        anexos=list(anexos),
        source_path=arquivo,
        anexos_abs=anexos_abs,
        anexos_ausentes=ausentes,
    )


def load_requests(inbox_dir: str | Path) -> tuple[list[Request], list[InvalidItem]]:
    """Lê todos os `*.json` da pasta (sem recursão) e separa válidos e inválidos. Nunca lança."""
    validos: list[Request] = []
    invalidos: list[InvalidItem] = []
    try:
        pasta = Path(inbox_dir).resolve()
        if not pasta.is_dir():
            log.warning("Pasta da inbox não encontrada: %s", pasta)
            return validos, invalidos
        arquivos = sorted(p for p in pasta.glob("*.json") if p.is_file())
    except OSError as exc:
        log.error("Não foi possível listar a inbox %s: %s", inbox_dir, exc)
        return validos, invalidos

    vistos: set[str] = set()
    for arquivo in arquivos:
        try:
            item = _validar(arquivo, pasta, vistos)
        except Exception as exc:  # caminho seguro: um arquivo ruim não derruba a leitura
            item = InvalidItem(arquivo, f"erro inesperado na validação: {type(exc).__name__}: {exc}")
        if isinstance(item, InvalidItem):
            log.warning("Solicitação rejeitada (%s): %s", arquivo.name, item.reason)
            invalidos.append(item)
        else:
            validos.append(item)
    log.info("Inbox %s: %d válida(s), %d inválida(s)", pasta, len(validos), len(invalidos))
    return validos, invalidos


__all__ = ["Request", "InvalidItem", "load_requests"]
