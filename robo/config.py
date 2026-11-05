"""Carrega config.yaml e variáveis do .env (chaves nunca ficam no código)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # python-dotenv é opcional
    pass


@lru_cache(maxsize=1)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def path(key: str) -> Path:
    """Caminho absoluto de uma entrada de `paths` do config."""
    p = Path(load_config()["paths"][key])
    return p if p.is_absolute() else (ROOT / p).resolve()


def services() -> list[dict[str, Any]]:
    return load_config()["services"]


def service_by_id(service_id: str) -> dict[str, Any] | None:
    return next((s for s in services() if s["id"] == service_id), None)


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
