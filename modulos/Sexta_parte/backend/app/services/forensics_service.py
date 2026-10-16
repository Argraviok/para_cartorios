"""Análise forense de documentos: ELA (Error Level Analysis), metadados e inspeção VLM.

O ELA bruto acende naturalmente em bordas de texto e contornos (alta frequência). Para não
confundir isso com montagem, o nível de erro de cada bloco 16x16 é comparado aos blocos de textura
semelhante (mesma faixa de gradiente) e só desvios robustos (z-score via MAD) são apontados.
"""
import asyncio
import io
from dataclasses import dataclass, field

import cv2
import numpy as np
import pymupdf
from PIL import ExifTags, Image, ImageChops, ImageEnhance
from pydantic import BaseModel, Field

from app.schemas.fraud_schema import SuspiciousRegion, TamperingCheck
from app.services import vlm_client
from app.services.vlm_client import VLMError, VLMImage

ELA_QUALITY = 90
BLOCK = 16
Z_THRESHOLD = 4.0
N_TEXTURE_BINS = 12
MAX_DISPLAY_SIDE = 2400
EDITING_SOFTWARE = ("photoshop", "gimp", "paint.net", "pixlr", "canva", "affinity", "photopea",
                    "illustrator", "inkscape", "corel", "snapseed", "picsart", "ilovepdf", "pdf-xchange editor",
                    "foxit phantompdf", "sejda", "smallpdf")


class UnsupportedDocument(ValueError):
    pass


@dataclass
class LoadedDocument:
    image: Image.Image            # RGB, resolução original usada na análise
    source_format: str            # "JPEG", "PNG", "PDF/JPEG", "PDF/RASTER", ...
    ela_reliable: bool            # ELA só é confiável quando a origem é JPEG
    metadata_findings: list[str] = field(default_factory=list)


@dataclass
class ForensicsResult:
    check: TamperingCheck
    display_jpeg: bytes
    heatmap_jpeg: bytes
    ela_jpeg: bytes


# ---------------------------------------------------------------- carregamento

def load_document(data: bytes, filename: str = "") -> LoadedDocument:
    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        return _load_pdf(data)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedDocument("Arquivo não é uma imagem ou PDF válido") from exc
    fmt = (img.format or "DESCONHECIDO").upper()
    findings = _exif_findings(img)
    return LoadedDocument(image=img.convert("RGB"), source_format=fmt, ela_reliable=fmt in {"JPEG", "MPO"},
                          metadata_findings=findings)


def _load_pdf(data: bytes) -> LoadedDocument:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedDocument("PDF inválido ou corrompido") from exc
    if doc.page_count == 0:
        raise UnsupportedDocument("PDF sem páginas")
    findings: list[str] = []
    meta = doc.metadata or {}
    tool = " ".join(filter(None, [meta.get("producer"), meta.get("creator")])).lower()
    hit = next((s for s in EDITING_SOFTWARE if s in tool), None)
    if hit:
        findings.append(f"Metadados do PDF indicam passagem por software de edição ({hit}).")
    if meta.get("creationDate") and meta.get("modDate") and meta["creationDate"] != meta["modDate"]:
        findings.append("PDF foi modificado após a criação (datas de criação e modificação divergem).")
    if doc.page_count > 1:
        findings.append(f"PDF com {doc.page_count} páginas: apenas a 1ª página foi submetida à análise forense.")

    page = doc[0]
    images = page.get_images(full=True)
    # Digitalização típica: uma única imagem cobrindo a página. Extraímos o JPEG original para
    # preservar os artefatos de compressão (rasterizar destruiria a evidência de ELA).
    if len(images) == 1:
        extracted = doc.extract_image(images[0][0])
        if extracted and extracted.get("ext") in {"jpeg", "jpg"}:
            img = Image.open(io.BytesIO(extracted["image"])).convert("RGB")
            return LoadedDocument(img, "PDF/JPEG", True, findings)
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if len(images) > 1:
        findings.append("Página do PDF composta por várias imagens sobrepostas — padrão comum em montagens.")
    return LoadedDocument(img, "PDF/RASTER", False, findings)


def _exif_findings(img: Image.Image) -> list[str]:
    try:
        exif = img.getexif()
    except Exception:  # noqa: BLE001
        return []
    software = str(exif.get(ExifTags.Base.Software, "") or "")
    if any(s in software.lower() for s in EDITING_SOFTWARE):
        return [f"Metadados EXIF indicam edição pelo software '{software.strip()}'."]
    return []


# ---------------------------------------------------------------- ELA

def compute_ela(image_bytes: bytes, quality: int = ELA_QUALITY) -> bytes:
    """Error Level Analysis clássico: realça artefatos de compressão JPEG para identificar montagens."""
    original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return _ela_visual(original, quality)


def _resave(img: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def _ela_visual(original: Image.Image, quality: int) -> bytes:
    ela_image = ImageChops.difference(original, _resave(original, quality))
    max_diff = max(ex[1] for ex in ela_image.getextrema())
    scale = 255.0 / max_diff if max_diff else 1.0
    ela_image = ImageEnhance.Brightness(ela_image).enhance(scale)
    return _to_jpeg(ela_image)


def ela_anomaly_map(img: Image.Image, quality: int = ELA_QUALITY) -> np.ndarray:
    """Mapa (por bloco) de z-scores robustos do erro de recompressão, descontada a textura local."""
    orig = np.asarray(img, dtype=np.float32)
    resaved = np.asarray(_resave(img, quality), dtype=np.float32)
    diff = np.abs(orig - resaved).max(axis=2)

    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY).astype(np.float32)
    grad = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))

    hb, wb = diff.shape[0] // BLOCK, diff.shape[1] // BLOCK
    if hb < 4 or wb < 4:
        raise UnsupportedDocument("Imagem pequena demais para análise forense")

    def blocks(a: np.ndarray) -> np.ndarray:
        return a[: hb * BLOCK, : wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).mean(axis=(1, 3))

    ela_b, grad_b = blocks(diff), blocks(grad)
    # Normalização condicional à textura: blocos são agrupados por faixa de gradiente (quantis) e
    # cada um é comparado à mediana/MAD da sua própria faixa. Texto e bordas têm erro e variância
    # naturalmente maiores; só o que foge do padrão da própria faixa é anômalo.
    g, e = grad_b.ravel(), ela_b.ravel()
    edges = np.unique(np.quantile(g, np.linspace(0, 1, N_TEXTURE_BINS + 1)))
    bins = np.clip(np.searchsorted(edges, g, side="right") - 1, 0, max(len(edges) - 2, 0))
    z = np.zeros_like(e)
    for b in np.unique(bins):
        sel = bins == b
        med = np.median(e[sel])
        mad = np.median(np.abs(e[sel] - med)) * 1.4826
        z[sel] = (e[sel] - med) / max(mad, 0.25, 0.08 * med)
    return z.reshape(hb, wb)


def find_regions(z: np.ndarray) -> list[SuspiciousRegion]:
    mask = (z > Z_THRESHOLD).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    regions = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        intensity = float(z[labels == i].mean())
        # Bloco isolado só conta se o desvio for extremo (reduz falso positivo por ruído).
        if area >= 2 or intensity > 2 * Z_THRESHOLD:
            regions.append(SuspiciousRegion(x=int(x * BLOCK), y=int(y * BLOCK), w=int(w * BLOCK),
                                            h=int(h * BLOCK), intensity=round(intensity, 2)))
    regions.sort(key=lambda r: r.intensity * r.w * r.h, reverse=True)
    return regions[:12]


def ela_score(z: np.ndarray, regions: list[SuspiciousRegion]) -> int:
    if not regions:
        return int(min(15, max(0.0, float(np.percentile(z, 99.5)) - 1) * 4))
    total_blocks = z.size
    area = sum(r.w * r.h for r in regions) / (BLOCK * BLOCK)
    frac = area / total_blocks
    top = max(r.intensity for r in regions)
    # Regiões fortes e compactas são o padrão de colagem; anomalia espalhada por >40% da imagem
    # costuma ser recompressão global, não montagem.
    score = 30 + min(45, (top - Z_THRESHOLD) * 6) + min(25, frac * 400)
    if frac > 0.4:
        score *= 0.5
    return int(max(0, min(100, score)))


def render_heatmap(img: Image.Image, z: np.ndarray, regions: list[SuspiciousRegion]) -> bytes:
    base = np.asarray(img)
    h, w = base.shape[:2]
    heat = np.clip(z, 0, 3 * Z_THRESHOLD) / (3 * Z_THRESHOLD)
    heat = cv2.resize(heat.astype(np.float32), (z.shape[1] * BLOCK, z.shape[0] * BLOCK),
                      interpolation=cv2.INTER_NEAREST)
    heat = cv2.GaussianBlur(heat, (0, 0), BLOCK / 2)
    full = np.zeros((h, w), np.float32)
    full[: heat.shape[0], : heat.shape[1]] = heat
    color = cv2.cvtColor(cv2.applyColorMap((full * 255).astype(np.uint8), cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(cv2.cvtColor(base, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB).astype(np.float32) * 0.85
    alpha = np.clip(full * 1.6, 0, 0.85)[..., None]
    out = (gray * (1 - alpha) + color.astype(np.float32) * alpha).astype(np.uint8)
    thickness = max(2, w // 600)
    for r in regions:
        cv2.rectangle(out, (r.x, r.y), (r.x + r.w, r.y + r.h), (255, 0, 0), thickness)
    return _to_jpeg(Image.fromarray(out))


def _to_jpeg(img: Image.Image, quality: int = 90) -> bytes:
    if max(img.size) > MAX_DISPLAY_SIDE:
        img = img.copy()
        img.thumbnail((MAX_DISPLAY_SIDE, MAX_DISPLAY_SIDE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _describe_region(r: SuspiciousRegion, width: int, height: int) -> str:
    cx, cy = (r.x + r.w / 2) / width, (r.y + r.h / 2) / height
    vert = "superior" if cy < 0.33 else "inferior" if cy > 0.66 else "central"
    horiz = "esquerda" if cx < 0.33 else "direita" if cx > 0.66 else "centro"
    return (f"Inconsistência de compressão digital na região {vert}/{horiz} "
            f"(x={r.x}, y={r.y}, {r.w}x{r.h}px, desvio {r.intensity:.1f}σ) — possível inserção ou colagem digital.")


# ---------------------------------------------------------------- VLM

class VLMDocumentReport(BaseModel):
    tampering_suspected: bool
    confidence: float = Field(ge=0, le=1)
    font_inconsistency: bool
    misaligned_characters: bool
    missing_security_features: bool
    findings: list[str]


VLM_DOC_SCHEMA = {
    "type": "object",
    "properties": {
        "tampering_suspected": {"type": "boolean"},
        "confidence": {"type": "number", "description": "0 a 1"},
        "font_inconsistency": {"type": "boolean"},
        "misaligned_characters": {"type": "boolean"},
        "missing_security_features": {"type": "boolean"},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tampering_suspected", "confidence", "font_inconsistency", "misaligned_characters",
                 "missing_security_features", "findings"],
    "additionalProperties": False,
}

VLM_DOC_PROMPT = """Você é um perito documentoscópico auxiliando um cartório brasileiro de Notas/Registro de Imóveis.
Analise o documento ({doc_type}) na PRIMEIRA imagem. A SEGUNDA imagem é um mapa de anomalias de ELA
(Error Level Analysis): áreas quentes/vermelhas e retângulos indicam compressão digital inconsistente.

Verifique objetivamente:
1. Tipografia: campos (nome, CPF, RG, data de nascimento, filiação, nº de registro) com fonte, peso,
   tamanho, kerning ou cor diferentes do restante do documento ou do padrão oficial do órgão expedidor.
2. Alinhamento: dígitos de RG/CPF/datas desalinhados da linha de base ou com espaçamento irregular.
3. Elementos de segurança esperados (ex.: RG — brasão, fundo numismático/guilloche, microletras;
   CNH — QR Code, padrão de fundo, holografia; procuração — selo/etiqueta de autenticidade, carimbo
   e sinal público do tabelião). Aponte ausência ou aspecto de impressão/colagem.
4. Correlação entre as regiões quentes do ELA e campos sensíveis do documento.

Seja conservador: não declare adulteração sem evidência visual concreta. Cada item de `findings`
deve ser uma frase objetiva em português citando o campo/região. Se nada for encontrado, retorne
findings vazio e tampering_suspected=false."""


async def _vlm_inspect(img_jpeg: bytes, heatmap_jpeg: bytes, doc_type: str) -> VLMDocumentReport:
    return await vlm_client.analyze(
        VLM_DOC_PROMPT.format(doc_type=doc_type),
        [VLMImage(data=img_jpeg, label="Documento:"), VLMImage(data=heatmap_jpeg, label="Mapa de anomalias ELA:")],
        VLM_DOC_SCHEMA,
        VLMDocumentReport,
    )


# ---------------------------------------------------------------- orquestração

def _run_local_analysis(data: bytes, filename: str):
    """Parte CPU-bound (ELA, mapas, metadados) — executada fora do event loop."""
    loaded = load_document(data, filename)
    img = loaded.image
    z = ela_anomaly_map(img)
    regions = find_regions(z)
    score = ela_score(z, regions)
    findings: list[str] = []

    if loaded.ela_reliable:
        findings += [_describe_region(r, img.width, img.height) for r in regions[:5]]
    else:
        # Sem compressão JPEG de origem, o ELA é apenas indicativo: pesa metade.
        score //= 2
        findings.append(f"Arquivo de origem {loaded.source_format}: ELA de baixa confiabilidade "
                        "(sem artefatos JPEG originais). Preferir a imagem original da câmera/scanner.")
        if regions:
            findings.append(f"{len(regions)} região(ões) com nível de erro atípico — avaliar visualmente no mapa.")

    if loaded.metadata_findings:
        findings += loaded.metadata_findings
        if any("software de edição" in f or "edição pelo software" in f for f in loaded.metadata_findings):
            score = min(100, score + 25)

    return loaded, regions, score, findings, _to_jpeg(img, 92), render_heatmap(img, z, regions), _ela_visual(img, ELA_QUALITY)


async def analyze_document(data: bytes, filename: str, doc_type: str) -> ForensicsResult:
    loaded, regions, score, findings, display_jpeg, heatmap_jpeg, ela_jpeg = await asyncio.to_thread(
        _run_local_analysis, data, filename)
    img = loaded.image

    vlm_used, vlm_error = False, None
    if vlm_client.is_enabled():
        try:
            report = await _vlm_inspect(display_jpeg, heatmap_jpeg, doc_type)
            vlm_used = True
            findings += [f"[VLM] {f}" for f in report.findings]
            flags = sum([report.font_inconsistency, report.misaligned_characters, report.missing_security_features])
            if report.tampering_suspected:
                score = max(score, int(40 + 50 * report.confidence))
            score = min(100, score + 8 * flags)
        except VLMError as exc:
            vlm_error = str(exc)
    else:
        findings.append("Análise tipográfica e de elementos de segurança não executada (VLM desabilitado).")

    status = "SUSPEITO" if score >= 50 else "INCONCLUSIVO" if score >= 25 else "APROVADO"
    check = TamperingCheck(
        status=status, score=score, findings=findings, suspicious_regions=regions,
        source_format=loaded.source_format, ela_reliable=loaded.ela_reliable,
        vlm_used=vlm_used, vlm_error=vlm_error, image_width=img.width, image_height=img.height,
    )
    return ForensicsResult(check=check, display_jpeg=display_jpeg, heatmap_jpeg=heatmap_jpeg, ela_jpeg=ela_jpeg)
