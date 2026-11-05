"""Integração com o assistente RAG (repositório citizentech-genai, pacote `citizen_rag`).

Ordem de busca:
1. pacote instalado no ambiente (`pip install -e ../genAI` ou `pip install -r requirements-integracao.txt`);
2. pasta irmã configurada em `paths.genai_path` (clone do repositório ao lado deste).
Se nenhum dos dois existir, o robô continua funcionando e responde por template.
"""
from __future__ import annotations

import importlib
import sys
from typing import Any

from .config import path


def importar_rag_assistant() -> tuple[type | None, str]:
    """Devolve (classe RAGAssistant ou None, origem/erro)."""
    try:
        mod = importlib.import_module("citizen_rag.rag")
        return mod.RAGAssistant, "pacote instalado"
    except ImportError:
        pass
    genai_dir = path("genai_path")
    if not genai_dir.exists():
        return None, f"citizen_rag não instalado e {genai_dir} não existe"
    if str(genai_dir) not in sys.path:
        sys.path.insert(0, str(genai_dir))
    try:
        mod = importlib.import_module("citizen_rag.rag")
        return mod.RAGAssistant, f"pasta {genai_dir}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def criar_rag() -> tuple[Any | None, str]:
    """Instancia o assistente usando o corpus mais recente coletado por este robô."""
    cls, origem = importar_rag_assistant()
    if cls is None:
        return None, origem
    try:
        return cls(corpus_path=path("corpus")), origem
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
