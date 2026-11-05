"""Classificador de intenção: qual serviço federal o cidadão quer (ou `fora_escopo`).

Modelo: TF-IDF de palavras (1–2-gramas) + TF-IDF de caracteres (2–5, `char_wb`, robusto a
erros de digitação e falta de acento) -> Regressão Logística multinomial.

- `train(labels_csv=None, out_path=None)`: treina com `data/synthetic/treino_classificador.csv`
  (colunas texto, service_id), mede por validação cruzada estratificada (5 dobras), salva o
  pipeline em `models/classifier.joblib` e devolve as métricas.
- `predict(text)`: mascara dados pessoais (`mask_pii`) e devolve (service_id ou "fora_escopo",
  confiança). Carrega o modelo sob demanda e treina automaticamente se o arquivo não existir.
  Quem chama compara a confiança com `classifier.min_confidence` e manda para revisão humana.
  Nunca lança exceção: em falha devolve (None, 0.0).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import path
from .privacy import mask_pii
from .resilience import get_logger

log = get_logger("classifier")

SEED = 42
_MODELO: dict[str, Any] | None = None
_LOCK = threading.Lock()


def _caminho_modelo(out_path: str | Path | None = None) -> Path:
    return Path(out_path) if out_path else path("models") / "classifier.joblib"


def _novo_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    feats = FeatureUnion([
        ("palavras", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), strip_accents="unicode",
                                     lowercase=True, sublinear_tf=True, min_df=1)),
        ("caracteres", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), strip_accents="unicode",
                                       lowercase=True, sublinear_tf=True, min_df=1)),
    ])
    clf = LogisticRegression(C=10.0, max_iter=3000, class_weight="balanced", random_state=SEED)
    return Pipeline([("tfidf", feats), ("clf", clf)])


def _carregar_treino(labels_csv: str | Path | None):
    import pandas as pd
    csv_path = Path(labels_csv) if labels_csv else path("synthetic") / "treino_classificador.csv"
    df = pd.read_csv(csv_path, encoding="utf-8")
    df = df.dropna(subset=["texto", "service_id"])
    df["texto"] = df["texto"].astype(str).map(mask_pii)
    return df, csv_path


def train(labels_csv: str | Path | None = None, out_path: str | Path | None = None) -> dict[str, Any]:
    """Treina, avalia por validação cruzada e salva o modelo. Devolve as métricas."""
    global _MODELO
    import joblib
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    t0 = time.perf_counter()
    df, csv_path = _carregar_treino(labels_csv)
    X, y = df["texto"].tolist(), df["service_id"].tolist()
    n_dobras = max(2, min(5, df["service_id"].value_counts().min()))
    cv = StratifiedKFold(n_splits=n_dobras, shuffle=True, random_state=SEED)
    y_pred = cross_val_predict(_novo_pipeline(), X, y, cv=cv)
    relatorio = classification_report(y, y_pred, output_dict=True, zero_division=0)
    metricas = {
        "n_amostras": len(X),
        "n_classes": int(df["service_id"].nunique()),
        "cv_dobras": int(n_dobras),
        "cv_acuracia": round(float(accuracy_score(y, y_pred)), 4),
        "cv_f1_macro": round(float(f1_score(y, y_pred, average="macro")), 4),
        "por_classe": {c: {"precisao": round(v["precision"], 3), "revocacao": round(v["recall"], 3),
                           "f1": round(v["f1-score"], 3), "suporte": int(v["support"])}
                       for c, v in relatorio.items() if isinstance(v, dict) and "support" in v
                       and c not in ("macro avg", "weighted avg")},
    }
    modelo = _novo_pipeline().fit(X, y)
    destino = _caminho_modelo(out_path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pacote = {"pipeline": modelo, "classes": list(modelo.classes_), "metricas": metricas,
              "treinado_em": datetime.now().isoformat(timespec="seconds"), "fonte": str(csv_path)}
    joblib.dump(pacote, destino)
    with _LOCK:
        _MODELO = pacote
    metricas["segundos"] = round(time.perf_counter() - t0, 2)
    metricas["modelo"] = str(destino)
    log.info("Classificador treinado (%d amostras): acurácia CV %.3f, F1 macro %.3f -> %s",
             len(X), metricas["cv_acuracia"], metricas["cv_f1_macro"], destino)
    return metricas


def _obter_modelo() -> dict[str, Any]:
    global _MODELO
    if _MODELO is None:
        with _LOCK:
            if _MODELO is None:
                destino = _caminho_modelo()
                if destino.is_file():
                    import joblib
                    try:
                        _MODELO = joblib.load(destino)
                        log.info("Classificador carregado de %s", destino)
                    except Exception as exc:  # arquivo corrompido/incompatível -> re-treina
                        log.warning("Modelo %s inválido (%s); treinando novamente", destino, exc)
        if _MODELO is None:
            log.info("Modelo do classificador não encontrado; treinando automaticamente")
            train()
    return _MODELO  # type: ignore[return-value]


def predict(text: str) -> tuple[str | None, float]:
    """(service_id ou "fora_escopo", confiança 0–1). Texto vazio ou falha -> (None, 0.0)."""
    if not text or not str(text).strip():
        return None, 0.0
    try:
        modelo = _obter_modelo()
        pipe = modelo["pipeline"]
        proba = pipe.predict_proba([mask_pii(str(text))])[0]
        i = int(proba.argmax())
        return str(pipe.classes_[i]), round(float(proba[i]), 4)
    except Exception as exc:  # caminho seguro: o robô manda para revisão humana
        log.exception("Falha ao classificar texto: %s", exc)
        return None, 0.0


def predict_top(text: str, k: int = 3) -> list[tuple[str, float]]:
    """Auxiliar (não faz parte do contrato): as k classes mais prováveis, útil para relatórios."""
    try:
        pipe = _obter_modelo()["pipeline"]
        proba = pipe.predict_proba([mask_pii(str(text))])[0]
        ordem = proba.argsort()[::-1][:k]
        return [(str(pipe.classes_[i]), round(float(proba[i]), 4)) for i in ordem]
    except Exception as exc:
        log.warning("predict_top falhou: %s", exc)
        return []


__all__ = ["train", "predict", "predict_top"]
