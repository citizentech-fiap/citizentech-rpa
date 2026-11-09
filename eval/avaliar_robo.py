"""Avalia a execução do robô contra o conjunto de teste rotulado.

Pré-requisito: `python run_robot.py --carregar-teste` (processa data/synthetic/inbox_teste).
Uso: python eval/avaliar_robo.py
Saídas: eval/resultados_robo.md e eval/resultados_robo.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from robo.config import path, service_by_id  # noqa: E402


def _set(v) -> set[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return set()
    return {x.strip() for x in str(v).split(";") if x.strip()}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Avalia uma planilha contra o teste rotulado")
    ap.add_argument("--planilha", type=Path, default=path("control_sheet"))
    args = ap.parse_args()
    labels = pd.read_csv(path("synthetic") / "labels.csv", dtype=str).fillna("")
    xl = pd.read_excel(args.planilha, sheet_name=None)
    sol = xl["solicitacoes"].astype(object).drop_duplicates("request_id", keep="last").set_index("request_id")
    inval = set(Path(a).stem for a in xl.get("invalidas", pd.DataFrame(columns=["arquivo"]))["arquivo"].dropna())

    linhas = []
    for _, lab in labels.iterrows():
        rid = lab["request_id"]
        row = {"request_id": rid, "categoria": lab["categoria"], "servico_real": lab["service_id"],
               "decisao_esperada": lab["resultado_esperado"]}
        if rid in sol.index:
            p = sol.loc[rid]
            row.update(servico_previsto=p.get("service_id") if pd.notna(p.get("service_id")) else "",
                       confianca=float(p.get("confianca") or 0), decisao=p.get("decisao"),
                       fonte_resposta=p.get("fonte_resposta"))
            svc = service_by_id(lab["service_id"])
            if svc and row["servico_previsto"] == lab["service_id"] and lab["categoria"] in ("tipico", "docs_faltando"):
                req = set(svc["documentos_exigidos"])
                esperado = _set(lab["docs_presentes"]) & req
                previsto = _set(p.get("docs_presentes")) & req
                row["docs_ok"] = esperado == previsto
                row["docs_esperados"] = ";".join(sorted(esperado))
                row["docs_previstos"] = ";".join(sorted(previsto))
        elif rid in inval:
            row.update(decisao="invalido", servico_previsto="")
        else:
            row.update(decisao="nao_processado", servico_previsto="")
        row["decisao_ok"] = row["decisao"] == row["decisao_esperada"]
        linhas.append(row)

    df = pd.DataFrame(linhas)
    out_dir = ROOT / "eval"
    df.to_csv(out_dir / "resultados_robo.csv", index=False, encoding="utf-8")

    # Pedidos ambíguos: qualquer um dos dois serviços plausíveis conta como acerto de classificação
    alt = labels.set_index("request_id")["observacao"].str.extract(r"alternativa=(\w+)")[0]
    df["aceitos"] = df.apply(lambda r: {r["servico_real"]} | (
        {alt[r["request_id"]]} if isinstance(alt.get(r["request_id"]), str) else set()), axis=1)
    df["servico_ok"] = df.apply(lambda r: r["servico_previsto"] in r["aceitos"], axis=1)
    cls = df[df["categoria"].isin(["tipico", "docs_faltando", "ilegivel", "ambiguo"])]
    acc_cls = cls["servico_ok"].mean()
    # Erro grave: o robô respondeu sozinho ao cidadão sobre o serviço errado (ou respondeu algo fora de escopo)
    resolvidos = df[df["decisao"] == "resolvido"]
    graves = resolvidos[~resolvidos["servico_ok"] | (resolvidos["categoria"] == "fora_escopo")]
    # Erro seguro: mandou para revisão humana algo que poderia ter resolvido
    seguros = df[(df["decisao"] == "revisao_humana") & (df["decisao_esperada"] == "resolvido")]
    fe = df[df["categoria"] == "fora_escopo"]
    fe_ok = (fe["decisao"] == "revisao_humana").mean() if len(fe) else float("nan")
    docs = df[df.get("docs_ok").notna()] if "docs_ok" in df else df.iloc[0:0]
    acc_docs = docs["docs_ok"].mean() if len(docs) else float("nan")
    acc_dec = df["decisao_ok"].mean()

    md = ["# Avaliação do robô — conjunto de teste sintético rotulado", "",
          f"Amostra: **{len(df)} solicitações** ({', '.join(f'{k}: {v}' for k, v in df['categoria'].value_counts().items())}).", "",
          "| Métrica | Resultado | n |", "|---|---|---|",
          f"| Acurácia da classificação do serviço (exceto inválidas e fora de escopo) | {acc_cls:.1%} | {len(cls)} |",
          f"| Fora de escopo encaminhado para revisão humana | {fe_ok:.1%} | {len(fe)} |",
          f"| Conferência de documentos correta (OCR, quando o serviço foi acertado) | {acc_docs:.1%} | {len(docs)} |",
          f"| Decisão final correta (resolvido / revisão humana / inválido) | {acc_dec:.1%} | {len(df)} |",
          f"| **Erro grave**: resposta automática sobre o serviço errado | {len(graves)} de {len(resolvidos)} "
          f"respostas automáticas ({len(graves) / max(len(resolvidos), 1):.1%}) | {len(resolvidos)} |",
          f"| Erro seguro: revisão humana desnecessária | {len(seguros)} | {len(df)} |", "",
          "Pedidos ambíguos: qualquer um dos dois serviços plausíveis conta como acerto de classificação, mas a "
          "decisão esperada é revisão humana.", "",
          "Limiar congelado na validação: razão p1/p2 < 3,5; confiança mínima 0,45. "
          "Veja [calibração](calibracao_ambiguidade.md). Nenhuma varredura de limiares no teste.", "",
          "## Decisão por categoria", "",
          df.groupby("categoria")["decisao_ok"].agg(["mean", "count"]).rename(
              columns={"mean": "acerto", "count": "n"}).to_markdown(floatfmt=".2f"), "",
          "## Matriz de confusão da classificação", "",
          pd.crosstab(cls["servico_real"], cls["servico_previsto"].replace("", "(nenhum)")).to_markdown(), "",
          "## Erros", ""]
    erros = df[~df["decisao_ok"] | (df.get("docs_ok") == False)]  # noqa: E712
    cols = [c for c in ["request_id", "categoria", "servico_real", "servico_previsto", "confianca",
                        "decisao_esperada", "decisao", "docs_esperados", "docs_previstos"] if c in erros]
    md.append(erros[cols].to_markdown(index=False) if len(erros) else "Nenhum erro na amostra.")
    (out_dir / "resultados_robo.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    from robo.resilience import get_logger
    get_logger("avaliacao").info("\n%s", "\n".join(md[:24]))


if __name__ == "__main__":
    main()
