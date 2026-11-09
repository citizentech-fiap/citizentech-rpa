"""Saídas do robô: e-mail de resposta (.eml), planilha de controle e relatório de execução."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

from .config import env, load_config, path
from .resilience import get_logger

log = get_logger("outputs")

SHEETS = {
    "solicitacoes": ["run_id", "request_id", "data_envio", "service_id", "confianca", "segunda_opcao",
                     "decisao", "motivo",
                     "docs_presentes", "docs_faltantes", "docs_ilegiveis", "anexos_ausentes",
                     "fonte_resposta", "motivo_fallback", "eml", "tempo_s", "municipio", "uf", "cod_ibge",
                     "status_email", "erro_email"],
    "revisao_humana": ["run_id", "request_id", "motivo", "service_id", "confianca", "status",
                      "municipio", "uf", "cod_ibge", "desfecho", "responsavel", "fechado_em", "observacao"],
    "execucoes": ["run_id", "inicio", "fim", "lidas", "invalidas", "resolvidas", "revisao_humana",
                  "falhas", "puladas_duplicadas", "corpus_atualizados", "corpus_cache", "corpus_falhas",
                  "rag_disponivel", "motivo_rag"],
    "invalidas": ["run_id", "arquivo", "motivo"],
}


def write_eml(request: Any, subject: str, body: str, resultado: dict | None = None) -> Path:
    """Gera o e-mail de resposta. Por padrão só grava o rascunho; envio real é opcional via .env."""
    msg = EmailMessage()
    cfg = load_config()["email"]
    resultado = resultado if resultado is not None else {}
    resultado.update(status_email="rascunho", erro_email="")
    msg["From"] = cfg.get("sender", "atendimento-citizentech@exemplo.gov.br")
    msg["To"] = getattr(request, "email", "") or "cidadao@exemplo.com"
    msg["Subject"] = subject
    nome = (getattr(request, "nome", "") or "cidadão(ã)").split()[0]
    msg.set_content(f"Olá, {nome}!\n\n{body}\n\n—\nAtendimento automatizado CitizenTech "
                    "(protótipo acadêmico). Confira sempre a fonte oficial.")
    out = path("outbox") / f"{request.request_id}.eml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(msg))
    if cfg.get("send"):
        try:
            _send_smtp(msg)
            resultado["status_email"] = "enviado"
        except Exception as exc:  # e-mail falhou: rascunho continua em outbox/
            log.error("Envio SMTP falhou para %s, rascunho mantido: %s", request.request_id, exc)
            resultado.update(status_email="falha", erro_email=type(exc).__name__)
    return out


def _send_smtp(msg: EmailMessage) -> None:
    cfg = load_config()["email"]
    user, pwd = env("SMTP_USER"), env("SMTP_PASSWORD")
    if bool(user) != bool(pwd):
        raise RuntimeError("Informe SMTP_USER e SMTP_PASSWORD juntos")
    with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=20) as s:
        if cfg.get("starttls", True):
            s.starttls()
        if user and pwd:
            s.login(user, pwd)
        s.send_message(msg)


class ControlSheet:
    """Planilha de controle (controle.xlsx). Linhas de uma mesma request_id são atualizadas, não duplicadas."""

    def __init__(self, file: Path | None = None):
        self.file = file or path("control_sheet")
        self.file.parent.mkdir(parents=True, exist_ok=True)
        if self.file.exists():
            try:
                self.wb = load_workbook(self.file)
            except Exception as exc:  # planilha corrompida: guarda cópia e recria
                bad = self.file.with_suffix(".corrompida.xlsx")
                self.file.replace(bad)
                log.error("controle.xlsx ilegível (%s); movida para %s e recriada", exc, bad.name)
                self.wb = Workbook()
        else:
            self.wb = Workbook()
        for name, header in SHEETS.items():
            if name not in self.wb.sheetnames:
                ws = self.wb.create_sheet(name)
                ws.append(header)
            else:
                # Migra planilhas anteriores sem alterar as colunas e linhas já existentes.
                ws = self.wb[name]
                existentes = [c.value for c in ws[1]]
                for coluna in header:
                    if coluna not in existentes:
                        ws.cell(1, ws.max_column + 1, coluna)
        if "Sheet" in self.wb.sheetnames and len(self.wb.sheetnames) > len(SHEETS):
            del self.wb["Sheet"]

    def upsert(self, sheet: str, row: dict, key: str | None = "request_id") -> None:
        ws = self.wb[sheet]
        header = [c.value for c in ws[1]]
        values = [_cell(row.get(h)) for h in header]
        if key and key in header:
            idx = header.index(key)
            for r in ws.iter_rows(min_row=2):
                if r[idx].value == row.get(key):
                    if sheet == "revisao_humana" and r[header.index("status")].value == "fechado":
                        return  # uma nova execução nunca reabre nem apaga o desfecho humano
                    for c, v in zip(r, values):
                        c.value = v
                    return
        ws.append(values)

    def save(self) -> None:
        try:
            self.wb.save(self.file)
        except PermissionError:  # planilha aberta no Excel: salva com outro nome
            alt = self.file.with_name(self.file.stem + "_novo.xlsx")
            self.wb.save(alt)
            log.error("controle.xlsx está aberta em outro programa; salvo em %s", alt.name)


def _cell(v: Any) -> Any:
    if isinstance(v, (list, tuple, set)):
        return "; ".join(map(str, v))
    return v


def write_report(summary: dict, resultados: list[dict], invalidas: list[dict]) -> Path:
    out = path("reports_dir") / f"relatorio_{summary['run_id']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    linhas = [
        f"# Relatório de execução {summary['run_id']}",
        "",
        f"- Início: {summary['inicio']}  |  Fim: {summary['fim']}",
        f"- **RAG disponível: {summary.get('rag_disponivel')} — {summary.get('motivo_rag')}**",
        f"- Solicitações lidas: {summary['lidas']}  |  inválidas: {summary['invalidas']}  |  "
        f"duplicadas puladas: {summary['puladas_duplicadas']}",
        f"- Resolvidas automaticamente: {summary['resolvidas']}  |  revisão humana: {summary['revisao_humana']}  |  "
        f"falhas: {summary['falhas']}",
        f"- Base de serviços: {summary['corpus_atualizados']} atualizados, {summary['corpus_cache']} via cache, "
        f"{summary['corpus_falhas']} falhas",
        "",
        "| request_id | serviço | confiança | decisão | faltantes | resposta | motivo |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        linhas.append(f"| {r['request_id']} | {r.get('service_id') or '-'} | {r.get('confianca', 0):.2f} | "
                      f"{r['decisao']} | {_cell(r.get('docs_faltantes')) or '-'} | {r.get('fonte_resposta') or '-'} | "
                      f"{r.get('motivo') or ''} |")
    if invalidas:
        linhas += ["", "## Entradas inválidas", ""]
        linhas += [f"- `{i['arquivo']}`: {i['motivo']}" for i in invalidas]
    out.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return out
