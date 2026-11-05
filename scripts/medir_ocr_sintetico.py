"""Mede identificação dos anexos sintéticos, sem executar o robô ou escrever em eval/output.

Uso: ..\\.venv\\Scripts\\python scripts\\medir_ocr_sintetico.py
O nome do anexo fornece somente o gabarito; a identificação usa exclusivamente o texto OCR.
Casos inválidos ficam fora da medição, pois seus anexos não possuem gabarito de leitura.
"""
from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robo.config import load_config, path, services  # noqa: E402
from robo.ocr import check_documents  # noqa: E402
from robo.resilience import get_logger  # noqa: E402

log = get_logger("medicao_ocr_sintetico")


def main() -> int:
    base = path("synthetic")
    try:
        with (base / "labels.csv").open(encoding="utf-8", newline="") as fh:
            labels = list(csv.DictReader(fh))
    except (OSError, UnicodeError, csv.Error) as exc:
        log.error("Não foi possível ler o gabarito: %s", exc)
        return 2
    catalogo = {s["id"] for s in services()} | {"fora_escopo"}
    if {r.get("service_id") for r in labels} != catalogo:
        log.error("Gabarito pertence a outro catálogo; gere os dados antes de medir o OCR")
        return 2
    tipos = list(load_config()["document_types"])
    total, acertos = Counter(), Counter()
    degradados, rejeitados = 0, 0
    for row in labels:
        if row["categoria"] == "invalido":
            continue
        rid = row["request_id"]
        ruins = set(filter(None, row["docs_ilegiveis"].split(";")))
        presentes = set(filter(None, row["docs_presentes"].split(";")))
        arquivos = sorted((base / "inbox_teste" / "anexos").glob(f"{rid}_*"))
        esperados = {p.name: p.stem.removeprefix(rid + "_") for p in arquivos}
        if set(esperados.values()) != presentes | ruins:
            log.error("Anexos divergentes do gabarito em %s; gere novamente os dados", rid)
            return 2
        resultado = check_documents(arquivos, tipos)
        for det in resultado.detalhes:
            esperado = esperados[det["arquivo"]]
            if esperado in ruins:
                degradados += 1
                rejeitados += det["status"] == "ilegivel"
                continue
            total[esperado] += 1
            correto = det["tipo"] == esperado and det["status"] == "identificado"
            acertos[esperado] += correto
            if not correto:
                log.warning("Erro em %s: esperado=%s, identificado=%s, status=%s",
                            det["arquivo"], esperado, det["tipo"], det["status"])
    n, certos = sum(total.values()), sum(acertos.values())
    if not n:
        log.error("Nenhum anexo legível disponível para medir")
        return 2
    log.info("Acurácia de identificação nos anexos legíveis: %d/%d (%.2f%%)", certos, n, 100 * certos / n)
    for tipo in tipos:
        log.info("Tipo %s: %d/%d", tipo, acertos[tipo], total[tipo])
    log.info("Degradados rejeitados como ilegíveis: %d/%d (medida separada da identificação)", rejeitados, degradados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
