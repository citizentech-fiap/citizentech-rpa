"""Calibra apenas na validação. Teste e treino são lidos só para detectar textos repetidos."""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robo.classifier import predict_top
from robo.config import load_config, path
from robo.resilience import get_logger


def normalizar(texto):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKD", texto.casefold())))


def textos(pasta):
    resultado = set()
    for arquivo in pasta.glob("*.json"):
        try:
            texto = json.loads(arquivo.read_text(encoding="utf-8" )).get("texto", "")
            if texto.strip():
                resultado.add(normalizar(texto))
        except ValueError:
            pass
    return resultado


def main():
    base = path("synthetic")
    validacao = textos(base / "inbox_validacao")
    teste = textos(base / "inbox_teste")
    with (base / "treino_classificador.csv").open(encoding="utf-8") as fh:
        treino = {normalizar(r["texto"]) for r in csv.DictReader(fh)}
    intersecoes = len(validacao & treino), len(validacao & teste)
    if any(intersecoes):
        raise ValueError(f"Sobreposição de textos: {intersecoes}")
    with (base / "labels_validacao.csv").open(encoding="utf-8") as fh:
        labels = list(csv.DictReader(fh))
    dados = []
    for lab in labels:
        pedido = json.loads((base / "inbox_validacao" / (lab["request_id"] + ".json")).read_text(encoding="utf-8"))
        top = predict_top(pedido["texto"], 2)
        dados.append((lab["categoria"], top[0][0], top[0][1], top[1][1]))
    n_amb = sum(c == "ambiguo" for c, *_ in dados)
    n_tip = len(dados) - n_amb
    linhas, escolhas = [], []
    for sinal, limiares in (("margem", [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]),
                             ("razao", [1.5, 2, 2.5, 3, 3.5, 4, 5])):
        for limiar in limiares:
            amb = tip = 0
            for categoria, sid, p1, p2 in dados:
                valor = p1 - p2 if sinal == "margem" else p1 / max(p2, 1e-12)
                revisao = sid == "fora_escopo" or p1 < load_config()["classifier"]["min_confidence"] or valor < limiar
                amb += categoria == "ambiguo" and revisao
                tip += categoria == "tipico" and revisao
            erro = ((n_amb - amb) / n_amb + tip / n_tip) / 2
            escolhas.append((erro, tip, limiar, sinal, amb))
            linhas.append(f"| {sinal} | {limiar:.2f} | {amb}/{n_amb} | {tip}/{n_tip} | {erro:.4f} |")
    erro, tip, limiar, sinal, amb = min(escolhas)
    md = ["# Calibração de ambiguidade — validação separada", "",
          "Semente 20261109; textos próprios em scripts/textos_validacao.py; mesmos gerador e documentos sintéticos.",
          f"Amostra: {n_tip} típicos e {n_amb} ambíguos. Sobreposição exata normalizada com treino: {intersecoes[0]}; com teste: {intersecoes[1]}.",
          "Verificação de sobreposição não utiliza rótulos nem previsões do teste. Não garante independência semântica.",
          "Confiança mínima mantida em 0,45. Revisão inclui escopo/confiança e o sinal candidato, sem OCR.",
          "Objetivo pré-definido: menor média entre taxa de ambíguos perdidos e taxa de típicos revisados; empate favorece menos típicos revisados e menor limiar.", "",
          "| Sinal | Limiar (<) | Ambíguos revisados | Típicos revisados | Erro balanceado |",
          "|---|---|---|---|---|", *linhas, "",
          f"Escolha congelada antes da avaliação do teste: **{sinal} < {limiar:.2f}**; erro balanceado {erro:.4f}.",
          "Limites: amostra pequena e sintética; várias frases explícitas, sem representar toda a linguagem real. Não se promete recuperar todos os ambíguos do teste."]
    (ROOT / "eval/calibracao_ambiguidade.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    get_logger("calibracao").info("Escolha: %s < %.2f; ambíguos %d/%d; típicos %d/%d", sinal, limiar, amb, n_amb, tip, n_tip)


if __name__ == "__main__":
    main()
