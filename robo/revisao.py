"""Lista e encerra a fila humana, preservando as colunas consumidas pelo dashboard."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import path
from .outputs import ControlSheet
from .resilience import get_logger

log = get_logger("revisao")
DESFECHOS = ("respondido", "encaminhado", "indeferido")


def listar(arquivo: Path | None = None) -> list[dict]:
    arquivo = arquivo or path("control_sheet")
    if not arquivo.exists():
        return []
    planilha = ControlSheet(arquivo)
    try:
        linhas = list(planilha.wb["revisao_humana"].values)
        return [dict(zip(linhas[0], linha)) for linha in linhas[1:]
                if linha[linhas[0].index("status")] == "pendente"]
    finally:
        planilha.wb.close()


def fechar(request_id: str, desfecho: str, responsavel: str, observacao: str = "",
           arquivo: Path | None = None) -> None:
    """Encerra exatamente uma pendência; falhas esperadas são ValueError/OSError."""
    if desfecho not in DESFECHOS or not responsavel.strip():
        raise ValueError("Informe um desfecho válido e um responsável não vazio.")
    arquivo = arquivo or path("control_sheet")
    if not arquivo.exists():
        raise ValueError(f"Pedido {request_id} inexistente na fila.")
    planilha = ControlSheet(arquivo)
    temporario = arquivo.with_suffix(".revisao.tmp.xlsx")
    try:
        ws = planilha.wb["revisao_humana"]
        cabecalho = [c.value for c in ws[1]]
        for linha in ws.iter_rows(min_row=2):
            if linha[cabecalho.index("request_id")].value != request_id:
                continue
            if linha[cabecalho.index("status")].value == "fechado":
                raise ValueError(f"Pedido {request_id} já fechado.")
            novos = {"status": "fechado", "desfecho": desfecho, "responsavel": responsavel.strip(),
                     "observacao": observacao.strip(),
                     "fechado_em": datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")}
            for chave, valor in novos.items():
                linha[cabecalho.index(chave)].value = valor
            planilha.wb.save(temporario)
            planilha.wb.close()
            temporario.replace(arquivo)
            return
        raise ValueError(f"Pedido {request_id} inexistente na fila.")
    finally:
        planilha.wb.close()
        if temporario.exists():
            temporario.unlink()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fila de revisão humana CitizenTech")
    acao = ap.add_mutually_exclusive_group(required=True)
    acao.add_argument("--listar", action="store_true")
    acao.add_argument("--fechar", metavar="REQUEST_ID")
    ap.add_argument("--desfecho", choices=DESFECHOS)
    ap.add_argument("--responsavel", default="")
    ap.add_argument("--observacao", default="")
    ap.add_argument("--planilha", type=Path, help="planilha alternativa, por exemplo uma cópia temporária")
    args = ap.parse_args(argv)
    try:
        if args.listar:
            pendentes = listar(args.planilha)
            log.info("%d pedido(s) pendente(s)", len(pendentes))
            for pedido in pendentes:
                log.info("%s | %s", pedido["request_id"], pedido.get("motivo", ""))
        else:
            fechar(args.fechar, args.desfecho, args.responsavel, args.observacao, args.planilha)
            log.info("Pedido %s fechado: %s", args.fechar, args.desfecho)
        return 0
    except (ValueError, OSError) as exc:
        log.error("Não foi possível concluir: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
