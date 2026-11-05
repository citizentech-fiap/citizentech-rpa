"""Ponto de entrada do robô CitizenTech.

Uso:
    python run_robot.py                    # processa tudo o que está em inbox/
    python run_robot.py --carregar-teste   # copia o conjunto sintético de teste para inbox/ e processa
    python run_robot.py --offline          # simula gov.br fora do ar (usa o cache da base)
    python run_robot.py --sem-genai        # responde só por template (sem chamar o LLM)

Fluxo: atualizar base gov.br -> ler inbox -> mascarar PII -> classificar serviço -> OCR dos anexos
-> gerar resposta (RAG ou template) -> e-mail + planilha + relatório -> mover arquivos.
Nenhuma falha individual interrompe a execução: tudo vai para o log e segue por um caminho seguro.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from robo import classifier, collector, ocr, outputs, responder
from robo.config import load_config, path, service_by_id
from robo.inbox import load_requests
from robo.resilience import get_logger, safe_call

BRT = timezone(timedelta(hours=-3))
log = get_logger("run")


def _now() -> str:
    return datetime.now(BRT).isoformat(timespec="seconds")


def _load_corpus() -> dict[str, dict]:
    corpus = {}
    f = path("corpus")
    if not f.exists():
        log.warning("Corpus %s não existe; respostas usarão só o catálogo do config", f)
        return corpus
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            corpus[rec["service_id"]] = rec
        except (json.JSONDecodeError, KeyError) as exc:
            log.error("Linha %d do corpus inválida: %s", n, exc)
    return corpus


def _registry() -> tuple[Path, dict]:
    f = path("processed") / "registry.json"
    try:
        return f, json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except json.JSONDecodeError:
        log.error("registry.json corrompido; recriando")
        return f, {}


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _move(src: Path, base: Path, dest_root: Path) -> None:
    """Move preservando o caminho relativo à inbox (json + anexos)."""
    try:
        rel = src.resolve().relative_to(base.resolve())
    except ValueError:
        rel = Path(src.name)
    dst = dest_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))


def processar(req, corpus: dict, cfg: dict) -> dict:
    t0 = time.perf_counter()
    r = {"request_id": req.request_id, "data_envio": getattr(req, "data_envio", ""),
         "anexos_ausentes": [Path(a).name for a in getattr(req, "anexos_ausentes", [])]}

    # IA 1: classificação do serviço (texto mascarado dentro do classificador)
    (service_id, conf), err = safe_call(classifier.predict, req.texto, default=(None, 0.0),
                                        step=f"classificar {req.request_id}")
    r.update(service_id=service_id, confianca=float(conf or 0.0))
    service = service_by_id(service_id) if service_id else None
    top2 = classifier.predict_top(req.texto, 2) if not err else []
    segunda = top2[1] if len(top2) > 1 else (None, 0.0)
    r["segunda_opcao"] = f"{segunda[0]} ({segunda[1]:.2f})" if segunda[0] else ""

    motivo_revisao = None
    if err:
        motivo_revisao = "falha na classificação"
    elif service is None:
        motivo_revisao = "pedido fora do escopo dos serviços atendidos"
    elif conf < cfg["classifier"]["min_confidence"]:
        motivo_revisao = f"serviço incerto (confiança {conf:.2f})"
    elif segunda[0] and conf - segunda[1] < cfg["classifier"].get("min_margin", 0.0):
        motivo_revisao = f"pedido ambíguo entre {service_id} e {segunda[0]}"

    # OCR: conferência de documentos contra a Carta de Serviço
    doc_check = None
    if service:
        doc_check, err = safe_call(ocr.check_documents, list(req.anexos_abs), service["documentos_exigidos"],
                                   default=None, step=f"ocr {req.request_id}")
        if doc_check is None:
            motivo_revisao = motivo_revisao or "falha na leitura dos anexos"
        else:
            r.update(docs_presentes=doc_check.presentes, docs_faltantes=doc_check.faltantes,
                     docs_ilegiveis=[Path(str(p)).name for p in doc_check.ilegiveis])
            if doc_check.ilegiveis and not motivo_revisao:
                motivo_revisao = "anexo ilegível"

    # Resposta
    if motivo_revisao:
        r.update(decisao="revisao_humana", motivo=motivo_revisao, fonte_resposta="template")
        corpo = responder.resposta_revisao(motivo_revisao)
        assunto = f"[{req.request_id}] Sua solicitação foi encaminhada a um atendente"
    else:
        resp, err = safe_call(responder.gerar_resposta, req.texto, service, corpus.get(service["id"]), doc_check,
                              default=None, step=f"responder {req.request_id}")
        if resp is None:  # nem o template funcionou: revisão humana
            r.update(decisao="revisao_humana", motivo="falha ao gerar resposta", fonte_resposta="-")
            corpo = responder.resposta_revisao("falha ao gerar resposta")
        else:
            faltam = bool(doc_check and doc_check.faltantes)
            r.update(decisao="resolvido", motivo="documentos faltando" if faltam else "",
                     fonte_resposta=resp.fonte, motivo_fallback=resp.motivo_fallback)
            corpo = resp.corpo
        assunto = f"[{req.request_id}] {service['nome']} — orientações"

    eml, err = safe_call(outputs.write_eml, req, assunto, corpo, step=f"eml {req.request_id}")
    r["eml"] = eml.name if eml else f"falha: {err}"
    r["tempo_s"] = round(time.perf_counter() - t0, 2)
    log.info("%s -> %s | %s (%.2f) | %s", req.request_id, r["decisao"], service_id, r["confianca"], r.get("motivo"))
    return r


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="Robô CitizenTech (RPA + IA)")
    ap.add_argument("--carregar-teste", action="store_true", help="copia data/synthetic/inbox_teste para inbox/")
    ap.add_argument("--offline", action="store_true", help="não acessa o gov.br (usa cache)")
    ap.add_argument("--sem-genai", action="store_true", help="responde só por template")
    ap.add_argument("--sem-coleta", action="store_true", help="não atualiza a base gov.br nesta execução")
    args = ap.parse_args(argv)

    cfg = load_config()
    if args.sem_genai:
        cfg["responder"]["use_genai"] = False
    run_id = datetime.now(BRT).strftime("%Y%m%d-%H%M%S")
    inicio = _now()
    log.info("===== Execução %s iniciada =====", run_id)
    inbox_dir = path("inbox")
    inbox_dir.mkdir(parents=True, exist_ok=True)

    if args.carregar_teste:
        src = path("synthetic") / "inbox_teste"
        if src.exists():
            shutil.copytree(src, inbox_dir, dirs_exist_ok=True)
            log.info("Conjunto de teste copiado de %s", src)
        else:
            log.error("Conjunto de teste não encontrado em %s (rode scripts/gerar_dados_sinteticos.py)", src)

    # 1. Base de conhecimento oficial
    coleta = None
    if not args.sem_coleta:
        coleta, _ = safe_call(collector.update_corpus, offline=True if args.offline else None,
                              default=None, step="atualizar base gov.br")
    corpus = _load_corpus()

    # 2. Inbox
    (validas, invalidas), _ = safe_call(load_requests, inbox_dir, default=([], []), step="ler inbox")
    reg_file, registry = _registry()
    sheet = outputs.ControlSheet()
    resultados, inval_rows, puladas, falhas = [], [], 0, 0

    for item in invalidas:
        motivo = item.reason
        inval_rows.append({"run_id": run_id, "arquivo": Path(item.source_path).name, "motivo": motivo})
        sheet.upsert("invalidas", inval_rows[-1], key="arquivo")
        safe_call(_move, Path(item.source_path), inbox_dir, path("failed"), step="mover inválido")
        (path("failed") / f"{Path(item.source_path).name}.motivo.txt").write_text(motivo, encoding="utf-8")

    # Pedido cujos anexos declarados não existem nenhum: não há o que conferir -> inválido
    sem_anexo = [q for q in validas if getattr(q, "anexos_ausentes", None) and not q.anexos_abs]
    for req in sem_anexo:
        validas.remove(req)
        motivo = "nenhum dos anexos declarados foi encontrado: " + ", ".join(req.anexos_ausentes)
        log.error("%s inválida: %s", req.request_id, motivo)
        inval_rows.append({"run_id": run_id, "arquivo": Path(req.source_path).name, "motivo": motivo})
        sheet.upsert("invalidas", inval_rows[-1], key="arquivo")
        safe_call(_move, Path(req.source_path), inbox_dir, path("failed"), step="mover inválido")
        (path("failed") / f"{Path(req.source_path).name}.motivo.txt").write_text(motivo, encoding="utf-8")
    n_invalidas = len(invalidas) + len(sem_anexo)

    for req in validas:
        src = Path(req.source_path)
        h = _hash(src)
        if h in registry:  # idempotência: mesma solicitação já processada
            log.info("%s já processada na execução %s; pulando", req.request_id, registry[h]["run_id"])
            puladas += 1
            safe_call(_move, src, inbox_dir, path("processed"), step="mover duplicada")
            continue
        r, err = safe_call(processar, req, corpus, cfg, default=None, step=f"processar {req.request_id}")
        if r is None:
            falhas += 1
            r = {"request_id": req.request_id, "decisao": "revisao_humana", "motivo": f"erro inesperado: {err}",
                 "confianca": 0.0}
        r["run_id"] = run_id
        resultados.append(r)
        sheet.upsert("solicitacoes", r)
        if r["decisao"] == "revisao_humana":
            sheet.upsert("revisao_humana", {**r, "status": "pendente"})
        registry[h] = {"request_id": req.request_id, "run_id": run_id}
        for p in [src, *req.anexos_abs]:
            if Path(p).exists():
                safe_call(_move, Path(p), inbox_dir, path("processed"), step="mover processada")

    summary = {
        "run_id": run_id, "inicio": inicio, "fim": _now(),
        "lidas": len(validas) + n_invalidas, "invalidas": n_invalidas,
        "resolvidas": sum(r["decisao"] == "resolvido" for r in resultados),
        "revisao_humana": sum(r["decisao"] == "revisao_humana" for r in resultados),
        "falhas": falhas, "puladas_duplicadas": puladas,
        "corpus_atualizados": getattr(coleta, "atualizados", 0) if coleta else 0,
        "corpus_cache": len(getattr(coleta, "usou_cache", []) or []) if coleta else 0,
        "corpus_falhas": len(getattr(coleta, "falhas", []) or []) if coleta else (0 if args.sem_coleta else "erro"),
    }
    sheet.upsert("execucoes", summary, key="run_id")
    sheet.save()
    reg_file.parent.mkdir(parents=True, exist_ok=True)
    reg_file.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    rel, _ = safe_call(outputs.write_report, summary, resultados, inval_rows, step="relatório")
    log.info("===== Execução %s concluída: %s =====", run_id, {k: summary[k] for k in
             ("lidas", "invalidas", "resolvidas", "revisao_humana", "falhas", "puladas_duplicadas")})
    if rel:
        log.info("Relatório: %s", rel)
    summary["resultados"] = resultados
    return summary


if __name__ == "__main__":
    main()
