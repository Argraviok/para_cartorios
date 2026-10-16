"""Cotejo de assinatura (título x cartão de firma).

Heurística de visão computacional sobre atributos grafotécnicos estáticos: inclinação axial,
proporcionalidade, densidade de tinta, interrupções do traço (levantamentos de caneta),
espessura/regularidade do traço e forma global (HOG + perfis de projeção). Opcionalmente
combinada com um VLM. É ferramenta de triagem — não substitui exame grafotécnico pericial.
"""
import math
from dataclasses import dataclass

import cv2
import numpy as np
from pydantic import BaseModel, Field

from app.schemas.fraud_schema import SignatureCheck
from app.services import vlm_client
from app.services.vlm_client import VLMError, VLMImage

NORM_W, NORM_H = 256, 64
WEIGHTS = {
    "forma_global": 0.30,
    "perfis_projecao": 0.15,
    "inclinacao": 0.15,
    "proporcao": 0.10,
    "interrupcoes_traco": 0.12,
    "densidade_tinta": 0.08,
    "espessura_traco": 0.05,
    "regularidade_traco": 0.05,
}
COMPATIBLE_MIN = 70
DIVERGENT_MAX = 45


class InvalidSignatureImage(ValueError):
    pass


@dataclass
class SignatureFeatures:
    mask: np.ndarray        # tinta=255, recortada
    aspect: float
    slant_deg: float
    density: float
    components: int
    stroke_ratio: float     # espessura média / altura
    stroke_cv: float        # variação da espessura (proxy de variação de pressão)
    hog: np.ndarray
    proj_h: np.ndarray
    proj_v: np.ndarray


def _binarize(data: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if arr is None:
        raise InvalidSignatureImage("Imagem de assinatura inválida")
    if max(arr.shape) > 2000:
        f = 2000 / max(arr.shape)
        arr = cv2.resize(arr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    blur = cv2.GaussianBlur(arr, (3, 3), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if mask.mean() > 127:  # tinta clara em fundo escuro
        mask = 255 - mask
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = max(8, int(mask.size * 0.0002))
    clean = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            clean[labels == i] = 255
    ys, xs = np.nonzero(clean)
    if len(xs) < 50:
        raise InvalidSignatureImage("Nenhum traço de assinatura detectado na imagem")
    return clean[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]


def extract_features(data: bytes) -> SignatureFeatures:
    mask = _binarize(data)
    h, w = mask.shape
    m = cv2.moments(mask, binaryImage=True)
    slant = math.degrees(math.atan2(m["mu11"], m["mu02"])) if m["mu02"] else 0.0

    # Componentes após leve dilatação: aproxima o número de levantamentos da caneta.
    k = max(1, int(round(h * 0.02)))
    merged = cv2.dilate(mask, np.ones((k, k), np.uint8))
    components = cv2.connectedComponents(merged, connectivity=8)[0] - 1

    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    skel = _skeleton(mask)
    widths = dist[skel > 0] * 2
    widths = widths[widths > 0]
    stroke_mean = float(widths.mean()) if widths.size else 1.0
    stroke_cv = float(widths.std() / stroke_mean) if widths.size else 0.0

    norm = cv2.resize(mask, (NORM_W, NORM_H), interpolation=cv2.INTER_AREA)
    norm = cv2.GaussianBlur(norm, (5, 5), 0)
    hog = _hog(norm)
    proj_h = norm.sum(axis=0).astype(np.float32)
    proj_v = norm.sum(axis=1).astype(np.float32)

    return SignatureFeatures(
        mask=mask, aspect=w / h, slant_deg=slant, density=float((mask > 0).mean()),
        components=int(components), stroke_ratio=stroke_mean / h, stroke_cv=stroke_cv,
        hog=hog, proj_h=proj_h, proj_v=proj_v,
    )


def _hog(img: np.ndarray, cell: int = 16, bins: int = 9) -> np.ndarray:
    """Histograma de gradientes orientados (sem sinal), normalizado por célula."""
    f = img.astype(np.float32)
    gx, gy = cv2.Sobel(f, cv2.CV_32F, 1, 0), cv2.Sobel(f, cv2.CV_32F, 0, 1)
    mag = np.hypot(gx, gy)
    ang = (np.degrees(np.arctan2(gy, gx)) % 180) / (180 / bins)
    idx = np.minimum(ang.astype(int), bins - 1)
    ch, cw = img.shape[0] // cell, img.shape[1] // cell
    hist = np.zeros((ch, cw, bins), np.float32)
    for b in range(bins):
        m = np.where(idx == b, mag, 0)[: ch * cell, : cw * cell]
        hist[..., b] = m.reshape(ch, cell, cw, cell).sum(axis=(1, 3))
    hist /= np.linalg.norm(hist, axis=2, keepdims=True) + 1e-6
    return hist.ravel()


def _skeleton(mask: np.ndarray) -> np.ndarray:
    if hasattr(cv2, "ximgproc"):
        return cv2.ximgproc.thinning(mask)
    skel = np.zeros_like(mask)
    img = mask.copy()
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while cv2.countNonZero(img):
        eroded = cv2.erode(img, kernel)
        skel |= cv2.subtract(img, cv2.dilate(eroded, kernel))
        img = eroded
    return skel


def _ratio_sim(a: float, b: float, k: float = 2.0) -> float:
    if a <= 0 or b <= 0:
        return 0.0
    return math.exp(-abs(math.log(a / b)) * k)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def compare_features(q: SignatureFeatures, ref: SignatureFeatures) -> dict[str, float]:
    cos = float(np.dot(q.hog, ref.hog) / (np.linalg.norm(q.hog) * np.linalg.norm(ref.hog) + 1e-9))
    profiles = (_corr(q.proj_h, ref.proj_h) + _corr(q.proj_v, ref.proj_v)) / 2
    return {
        "forma_global": float(np.clip((cos - 0.45) / 0.45, 0, 1)),
        "perfis_projecao": float(np.clip((profiles - 0.2) / 0.7, 0, 1)),
        "inclinacao": math.exp(-abs(q.slant_deg - ref.slant_deg) / 12.0),
        "proporcao": _ratio_sim(q.aspect, ref.aspect, 2.5),
        "interrupcoes_traco": math.exp(-abs(q.components - ref.components) / max(1.5, ref.components * 0.5)),
        "densidade_tinta": _ratio_sim(q.density, ref.density, 1.5),
        "espessura_traco": _ratio_sim(q.stroke_ratio, ref.stroke_ratio, 1.5),
        "regularidade_traco": math.exp(-abs(q.stroke_cv - ref.stroke_cv) * 3),
    }


def heuristic_score(metrics: dict[str, float]) -> int:
    return int(round(100 * sum(WEIGHTS[k] * v for k, v in metrics.items())))


def _observation(metrics: dict[str, float], q: SignatureFeatures, ref: SignatureFeatures, card: str) -> str:
    labels = {
        "forma_global": "morfologia geral dos gramas",
        "perfis_projecao": "distribuição de massa gráfica",
        "inclinacao": f"inclinação global ({q.slant_deg:+.0f}° vs {ref.slant_deg:+.0f}° no padrão)",
        "proporcao": f"proporcionalidade (largura/altura {q.aspect:.1f} vs {ref.aspect:.1f})",
        "interrupcoes_traco": f"continuidade do traço ({q.components} vs {ref.components} segmentos)",
        "densidade_tinta": "densidade de tinta",
        "espessura_traco": "calibre do traço",
        "regularidade_traco": "variação de calibre (pressão)",
    }
    weak = [labels[k] for k, v in sorted(metrics.items(), key=lambda kv: kv[1]) if v < 0.5][:3]
    strong = [labels[k] for k, v in sorted(metrics.items(), key=lambda kv: -kv[1]) if v >= 0.8][:2]
    parts = []
    if weak:
        parts.append(f"Divergências em relação ao cartão de autógrafo {card}: " + "; ".join(weak) + ".")
    if strong:
        parts.append("Convergências: " + "; ".join(strong) + ".")
    if q.stroke_cv < 0.25 and ref.stroke_cv >= 0.35:
        parts.append("Calibre do traço anormalmente uniforme — compatível com decalque/traçado lento.")
    return " ".join(parts) or "Sem divergências relevantes nos atributos medidos."


class VLMSignatureReport(BaseModel):
    match_score: int = Field(ge=0, le=100)
    divergent: bool
    observation: str


VLM_SIG_SCHEMA = {
    "type": "object",
    "properties": {
        "match_score": {"type": "integer", "description": "0 a 100"},
        "divergent": {"type": "boolean"},
        "observation": {"type": "string"},
    },
    "required": ["match_score", "divergent", "observation"],
    "additionalProperties": False,
}

VLM_SIG_PROMPT = """Você auxilia um escrevente de cartório no cotejo de firma. A PRIMEIRA imagem é a assinatura
lançada no título/contrato; a SEGUNDA é o padrão do cartão de autógrafo arquivado na serventia.
Compare: inclinação axial, proporcionalidade entre gramas, ataques e remates, ligações entre letras,
continuidade do ducto (paradas bruscas, retoques), calibre/pressão e sinais de decalque ou tremor.
Atribua match_score de 0 (incompatível) a 100 (plenamente compatível) e uma observação técnica e
objetiva em português (máx. 3 frases). Seja conservador; variações naturais de punho não são divergência."""


async def compare(query_bytes: bytes, card_bytes: bytes, card_label: str, card_id: str | None) -> SignatureCheck:
    q = extract_features(query_bytes)
    ref = extract_features(card_bytes)
    metrics = compare_features(q, ref)
    score = heuristic_score(metrics)
    observation = _observation(metrics, q, ref, card_label)
    # Assinaturas muito pequenas/pobres em traço reduzem a confiabilidade da medição.
    quality = min(1.0, min(cv2.countNonZero(q.mask), cv2.countNonZero(ref.mask)) / 3000)
    confidence = 0.55 * quality

    vlm_used, vlm_error = False, None
    if vlm_client.is_enabled():
        try:
            ok_q, enc_q = cv2.imencode(".png", 255 - q.mask)
            ok_r, enc_r = cv2.imencode(".png", 255 - ref.mask)
            report = await vlm_client.analyze(
                VLM_SIG_PROMPT,
                [VLMImage(data=enc_q.tobytes(), mime_type="image/png", label="Assinatura do título:"),
                 VLMImage(data=enc_r.tobytes(), mime_type="image/png", label="Cartão de autógrafo:")],
                VLM_SIG_SCHEMA, VLMSignatureReport,
            )
            vlm_used = True
            score = int(round(0.5 * score + 0.5 * report.match_score))
            observation = f"{observation} [VLM] {report.observation}"
            confidence = min(0.9, confidence + 0.25 if abs(report.match_score - heuristic_score(metrics)) < 20
                             else confidence)
        except VLMError as exc:
            vlm_error = str(exc)

    status = "APROVADO" if score >= COMPATIBLE_MIN else "DIVERGENTE" if score < DIVERGENT_MAX else "INCONCLUSIVO"
    return SignatureCheck(
        status=status, match_score=score, confidence=round(confidence, 2),
        metrics={k: round(v, 3) for k, v in metrics.items()}, observation=observation,
        signature_card_id=card_id, vlm_used=vlm_used, vlm_error=vlm_error,
    )


def crop_signature_png(data: bytes) -> bytes:
    """Normaliza a assinatura (recorte + fundo branco) para exibição lado a lado."""
    mask = _binarize(data)
    pad = cv2.copyMakeBorder(255 - mask, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    return cv2.imencode(".png", pad)[1].tobytes()
