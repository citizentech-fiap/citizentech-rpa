"""OCR dos anexos e conferência dos documentos exigidos por serviço.

- `extract_text(path)`: PDF com camada de texto -> pdfplumber; imagem ou PDF escaneado -> RapidOCR
  (motor em cache, carregado uma vez). Se `ocr.engine == "tesseract"` no config e o binário
  existir, usa pytesseract; senão registra aviso e cai no RapidOCR. Arquivo ausente ou
  corrompido -> `OcrResult(ok=False, error=...)`; nunca lança exceção.
- `identify_doc_type(text)`: pontuação por palavras-chave/expressões de cada tipo canônico de
  `document_types`, sem diferenciar acento/caixa e tolerante a ruído de OCR (comparação
  aproximada com difflib e busca sem espaços, pois o OCR às vezes cola palavras).
- `check_documents(attachments, required)`: roda OCR + identificação em cada anexo e devolve
  `DocCheck(presentes, faltantes, ilegiveis, detalhes)`.

Regras do DocCheck:
- anexo é ILEGÍVEL quando o OCR falha, quando o texto útil tem menos de `ocr.min_chars`
  caracteres ou quando nenhum tipo atinge `ocr.min_doc_score` (documento não reconhecido);
- `presentes`: tipos identificados (primeiro os exigidos, na ordem do serviço; depois os extras);
- `faltantes`: exigidos que não foram identificados em nenhum anexo legível;
- `ilegiveis`: nomes dos arquivos ilegíveis/não reconhecidos (o tipo deles é desconhecido);
- `detalhes`: um dicionário por arquivo (arquivo, metodo, ok, chars, tipo, score, status,
  motivo, segundos). O nome do arquivo nunca é usado para decidir o tipo.
"""
from __future__ import annotations

import difflib
import re
import shutil
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_config
from .resilience import get_logger

log = get_logger("ocr")

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
MIN_BOX_SCORE = 0.5      # caixas do RapidOCR com confiança menor são descartadas (lixo de ruído)
MAX_LADO = 1800          # imagens maiores são reduzidas (latência)
MAX_PAGINAS_PDF = 5


@dataclass
class OcrResult:
    text: str
    method: str
    ok: bool
    error: str | None = None


@dataclass
class DocCheck:
    presentes: list[str] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    ilegiveis: list[str] = field(default_factory=list)
    detalhes: list[dict[str, Any]] = field(default_factory=list)


def _cfg_ocr() -> dict[str, Any]:
    try:
        return load_config().get("ocr", {}) or {}
    except Exception as exc:  # config ausente não pode derrubar o OCR
        log.warning("Não foi possível ler config de OCR (%s); usando padrões", exc)
        return {}


# ---------------------------------------------------------------------------
# Motores de OCR
# ---------------------------------------------------------------------------
_ENGINE = None
_ENGINE_LOCK = threading.Lock()
_AVISOU_TESSERACT = False


def _rapidocr():
    """Instância única do RapidOCR (carregar o modelo custa ~1 s)."""
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                from rapidocr_onnxruntime import RapidOCR
                _ENGINE = RapidOCR()
                log.info("RapidOCR carregado")
    return _ENGINE


def _tesseract_disponivel() -> bool:
    global _AVISOU_TESSERACT
    try:
        import pytesseract
        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        if shutil.which(cmd) or Path(cmd).is_file():
            return True
        motivo = "binário tesseract não encontrado"
    except ImportError:
        motivo = "pytesseract não instalado"
    if not _AVISOU_TESSERACT:
        log.warning("ocr.engine=tesseract, mas %s; usando RapidOCR", motivo)
        _AVISOU_TESSERACT = True
    return False


def _preparar(img):
    from PIL import Image
    img = img.convert("RGB")
    w, h = img.size
    maior = max(w, h)
    if maior > MAX_LADO:
        f = MAX_LADO / maior
        img = img.resize((int(w * f), int(h * f)), Image.LANCZOS)
    elif maior < 500:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    return img


def _ocr_imagem(img) -> tuple[str, str]:
    """OCR de uma imagem PIL. Devolve (texto, método)."""
    img = _preparar(img)
    if str(_cfg_ocr().get("engine", "rapidocr")).lower() == "tesseract" and _tesseract_disponivel():
        import pytesseract
        try:
            return pytesseract.image_to_string(img, lang="por"), "tesseract"
        except pytesseract.TesseractError:
            return pytesseract.image_to_string(img), "tesseract"
    import numpy as np
    resultado, _ = _rapidocr()(np.asarray(img))
    if not resultado:
        return "", "rapidocr"
    caixas = []
    for box, txt, score in resultado:
        try:
            s = float(score)
        except (TypeError, ValueError):
            s = 0.0
        if s < MIN_BOX_SCORE or not str(txt).strip():
            continue
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        caixas.append(((sum(ys) / len(ys)), min(xs), str(txt)))
    # ordem de leitura: linhas (tolerância de 15 px) e, dentro da linha, da esquerda para a direita
    caixas.sort(key=lambda c: (round(c[0] / 15), c[1]))
    return "\n".join(c[2] for c in caixas), "rapidocr"


def _extrair_pdf(p: Path, min_chars: int) -> tuple[str, str]:
    import pdfplumber
    with pdfplumber.open(p) as pdf:
        paginas = pdf.pages[:MAX_PAGINAS_PDF]
        texto = "\n".join((pg.extract_text() or "") for pg in paginas)
        if len(_normalizar(texto).replace(" ", "")) >= min_chars:
            return texto, "pdfplumber"
        # PDF escaneado: rasteriza as páginas e faz OCR
        partes, metodo = [], "pdf_ocr"
        for pg in paginas:
            img = pg.to_image(resolution=150).original
            t, m = _ocr_imagem(img)
            partes.append(t)
            metodo = f"pdf_ocr_{m}"
        return "\n".join(partes), metodo


def extract_text(path: str | Path) -> OcrResult:
    """Extrai texto de imagem ou PDF. Nunca lança exceção."""
    p = Path(path)
    ext = p.suffix.lower()
    metodo = "pdfplumber" if ext == ".pdf" else "rapidocr"
    try:
        if not p.is_file():
            return OcrResult("", metodo, False, f"arquivo não encontrado: {p}")
        if p.stat().st_size == 0:
            return OcrResult("", metodo, False, "arquivo vazio")
        if ext == ".pdf":
            texto, metodo = _extrair_pdf(p, int(_cfg_ocr().get("min_chars", 20)))
        else:
            from PIL import Image
            with Image.open(p) as img:
                img.load()
                texto, metodo = _ocr_imagem(img)
        return OcrResult(texto.strip(), metodo, True, None)
    except Exception as exc:  # arquivo corrompido, formato não suportado, falha do motor
        msg = f"{type(exc).__name__}: {exc}"
        log.warning("Falha ao extrair texto de %s: %s", p.name, msg)
        return OcrResult("", metodo, False, msg)


# ---------------------------------------------------------------------------
# Identificação do tipo de documento
# ---------------------------------------------------------------------------
# (expressão, peso). Títulos têm peso alto; campos típicos somam pouco. Expressões genéricas
# que aparecem em vários documentos (ex.: o campo "CPF") não entram ou têm peso baixo.
PALAVRAS_CHAVE: dict[str, list[tuple[str, float]]] = {
    "documento_identidade": [
        ("registro geral", 0.6), ("carteira de identidade", 0.6), ("carteira nacional de habilitacao", 0.6),
        ("instituto de identificacao", 0.3), ("secretaria de seguranca publica", 0.3),
        ("data de expedicao", 0.2), ("naturalidade", 0.15), ("filiacao", 0.1), ("doc identidade", 0.3),
        ("departamento de transito", 0.2), ("habilitacao", 0.2), ("rg", 0.1),
    ],
    "cpf": [
        ("cadastro de pessoas fisicas", 0.7), ("comprovante de inscricao", 0.3), ("situacao cadastral", 0.3),
        ("receita federal", 0.3), ("data da inscricao", 0.15), ("n de inscricao", 0.1),
    ],
    "comprovante_residencia": [
        ("comprovante de residencia", 0.7), ("comprovante de endereco", 0.7), ("conta de energia", 0.4),
        ("conta de agua", 0.4), ("energia eletrica", 0.2), ("agua e esgoto", 0.2), ("consumo do mes", 0.2),
        ("kwh", 0.15), ("valor a pagar", 0.15), ("vencimento", 0.1), ("titular", 0.1), ("endereco", 0.1),
    ],
    "caf": [
        ("registro de inscricao no cadastro nacional da agricultura familiar", 0.8),
        ("cadastro nacional da agricultura familiar", 0.7), ("ricaf", 0.8),
        ("extrato do caf", 0.7), ("comprovante de inscricao no caf", 0.7),
        ("unidade familiar de producao agraria", 0.3), ("caf", 0.2),
    ],
    "comprovante_posse_terra": [
        ("contrato de arrendamento rural", 0.8), ("escritura publica de imovel rural", 0.8),
        ("declaracao de posse", 0.7), ("comprovante de posse", 0.7),
        ("sindicato dos trabalhadores rurais", 0.3), ("imovel rural", 0.2),
        ("propriedade da terra", 0.3), ("hectares", 0.1),
    ],
    "certidao_civil": [
        ("certidao de nascimento", 0.7), ("certidao de casamento", 0.7), ("registro civil das pessoas naturais", 0.4),
        ("registro civil", 0.2), ("cartorio", 0.2), ("matricula", 0.15), ("data do nascimento", 0.1),
        ("data do casamento", 0.1),
    ],
    "comprovante_renda": [
        ("nota fiscal de produtor rural", 0.8), ("declaracao de renda", 0.8),
        ("renda declarada", 0.2), ("rendimentos da agricultura familiar", 0.3),
        ("comprovante de rendimentos", 0.7), ("comprovante de renda", 0.7), ("contracheque", 0.6),
        ("holerite", 0.6), ("demonstrativo de pagamento", 0.5), ("salario bruto", 0.25),
        ("valor liquido", 0.2), ("descontos", 0.1), ("competencia", 0.1), ("rendimentos", 0.15),
    ],
}
FUZZY_MIN = 0.82         # similaridade mínima (difflib) para aceitar expressão com erro de OCR
FUZZY_MIN_LEN = 8        # expressões curtas (siglas) só valem com casamento exato
PESO_PROFUNDO = 0.4      # só expressões fortes (títulos) usam a busca aproximada no texto colado


def _normalizar(texto: str) -> str:
    """minúsculas, sem acento, só [a-z0-9] separados por um espaço."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    t = t.replace("º", " ").replace("°", " ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _forca(expr: str, norm: str, colado: str, tokens: list[str], profundo: bool = False) -> float:
    """Quanto a expressão aparece no texto: 1.0 exato; ~0.82–1.0 aproximado; 0 ausente."""
    if re.search(rf"\b{re.escape(expr)}\b", norm):
        return 1.0
    sem_espaco = expr.replace(" ", "")
    if len(sem_espaco) < FUZZY_MIN_LEN:
        return 0.0
    if sem_espaco in colado:
        return 1.0
    n = len(expr.split())
    melhor = 0.0
    sm = difflib.SequenceMatcher(autojunk=False)
    sm.set_seq2(sem_espaco)
    for tam in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(1, len(tokens) - tam + 1)):
            janela = "".join(tokens[i:i + tam])
            if abs(len(janela) - len(sem_espaco)) > max(3, len(sem_espaco) // 4):
                continue
            sm.set_seq1(janela)
            if sm.real_quick_ratio() < FUZZY_MIN or sm.quick_ratio() < FUZZY_MIN:
                continue
            r = sm.ratio()
            if r > melhor:
                melhor = r
                if melhor >= 0.97:
                    return melhor
    if melhor < FUZZY_MIN and profundo:
        # OCR que cola palavras ("CADASIRODEPESSOASTISICAS"): busca aproximada dentro do texto sem espaços
        L = len(sem_espaco)
        for tam in (L - 1, L, L + 1):
            for i in range(0, max(1, len(colado) - tam + 1)):
                sm.set_seq1(colado[i:i + tam])
                if sm.quick_ratio() < FUZZY_MIN:
                    continue
                r = sm.ratio()
                if r > melhor:
                    melhor = r
                    if melhor >= 0.95:
                        return melhor
    return melhor if melhor >= FUZZY_MIN else 0.0


def doc_scores(text: str) -> dict[str, float]:
    """Pontuação 0–1 de cada tipo canônico para o texto."""
    try:
        tipos = load_config().get("document_types", {}) or {}
    except Exception as exc:
        log.warning("Catálogo de documentos indisponível: %s", exc)
        return {}
    norm = _normalizar(text)
    if not norm:
        return {tipo: 0.0 for tipo in tipos}
    colado = norm.replace(" ", "")
    tokens = norm.split()
    scores = {}
    for tipo, descricao in tipos.items():
        exprs = PALAVRAS_CHAVE.get(tipo, [(_normalizar(descricao), 0.7)])
        total = sum(peso * _forca(expr, norm, colado, tokens, profundo=peso >= PESO_PROFUNDO) for expr, peso in exprs)
        scores[tipo] = round(min(1.0, total), 3)
    return scores


def identify_doc_type(text: str) -> tuple[str | None, float]:
    """Tipo canônico mais provável e sua pontuação (0–1). (None, 0.0) se nada casar."""
    scores = doc_scores(text)
    if not scores:
        return None, 0.0
    tipo, score = max(scores.items(), key=lambda kv: kv[1])
    if score <= 0:
        return None, 0.0
    return tipo, score


# ---------------------------------------------------------------------------
# Conferência dos documentos exigidos
# ---------------------------------------------------------------------------
def check_documents(attachments: list[Path], required: list[str]) -> DocCheck:
    """Confere os anexos contra a lista de tipos exigidos pelo serviço. Nunca lança exceção."""
    cfg = _cfg_ocr()
    min_chars = int(cfg.get("min_chars", 20))
    min_score = float(cfg.get("min_doc_score", 0.5))
    required = list(required or [])
    identificados: list[str] = []
    ilegiveis: list[str] = []
    detalhes: list[dict[str, Any]] = []

    for anexo in attachments or []:
        p = Path(anexo)
        t0 = time.perf_counter()
        res = extract_text(p)
        det: dict[str, Any] = {"arquivo": p.name, "caminho": str(p), "metodo": res.method, "ok": res.ok,
                               "chars": 0, "tipo": None, "score": 0.0, "status": "", "motivo": None}
        chars = len(_normalizar(res.text).replace(" ", ""))
        det["chars"] = chars
        if not res.ok:
            det.update(status="ilegivel", motivo=f"falha na leitura: {res.error}")
        elif chars < min_chars:
            det.update(status="ilegivel", motivo=f"texto insuficiente ({chars} < {min_chars} caracteres)")
        else:
            tipo, score = identify_doc_type(res.text)
            det.update(tipo=tipo, score=score)
            if tipo is None or score < min_score:
                det.update(status="ilegivel",
                           motivo=f"tipo de documento não reconhecido (melhor: {tipo}, score {score:.2f})")
            else:
                det["status"] = "identificado" if tipo in required else "nao_exigido"
                if tipo not in identificados:
                    identificados.append(tipo)
        det["segundos"] = round(time.perf_counter() - t0, 3)
        if det["status"] == "ilegivel":
            ilegiveis.append(p.name)
            log.info("Anexo %s ilegível/não reconhecido: %s", p.name, det["motivo"])
        detalhes.append(det)

    presentes = [t for t in required if t in identificados] + [t for t in identificados if t not in required]
    faltantes = [t for t in required if t not in identificados]
    return DocCheck(presentes=presentes, faltantes=faltantes, ilegiveis=ilegiveis, detalhes=detalhes)


__all__ = ["OcrResult", "DocCheck", "extract_text", "identify_doc_type", "check_documents", "doc_scores"]
