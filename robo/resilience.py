"""Utilitários de resiliência compartilhados: logger, retry com espera exponencial, execução segura."""
from __future__ import annotations

import functools
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
_CONFIGURED = False


def get_logger(name: str = "robo", log_file: str | Path | None = None) -> logging.Logger:
    """Logger único do robô: grava em logs/robot.log e no console."""
    global _CONFIGURED
    if not _CONFIGURED:
        path = Path(log_file) if log_file else ROOT / "logs" / "robot.log"
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        root = logging.getLogger("robo")
        root.setLevel(logging.INFO)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        try:  # console do Windows em cp1252 quebra acentos
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(fh)
        root.addHandler(sh)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("robo") else f"robo.{name}")


def retry(times: int = 3, backoff_s: float = 2.0,
          exceptions: Iterable[type[BaseException]] = (Exception,),
          logger: logging.Logger | None = None) -> Callable:
    """Decorator: tenta `times` vezes, esperando backoff_s * 2**(tentativa-1) entre as tentativas.
    Na última falha, relança a exceção para o chamador decidir o caminho seguro."""
    exc_tuple = tuple(exceptions)

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            log = logger or get_logger("retry")
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except exc_tuple as exc:  # noqa: PERF203
                    if attempt == times:
                        log.error("%s falhou após %d tentativas: %s", fn.__name__, times, exc)
                        raise
                    wait = backoff_s * 2 ** (attempt - 1)
                    log.warning("%s falhou (tentativa %d/%d): %s — nova tentativa em %.1fs",
                                fn.__name__, attempt, times, exc, wait)
                    time.sleep(wait)
        return wrapper
    return deco


def safe_call(fn: Callable, *args: Any, default: Any = None, step: str = "",
              logger: logging.Logger | None = None, **kwargs: Any) -> tuple[Any, str | None]:
    """Executa fn; em erro registra no log e devolve (default, mensagem_de_erro) sem interromper o robô."""
    log = logger or get_logger("safe")
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # caminho seguro: nunca derruba a execução inteira
        msg = f"{type(exc).__name__}: {exc}"
        log.exception("Falha na etapa %s: %s", step or fn.__name__, msg)
        return default, msg
