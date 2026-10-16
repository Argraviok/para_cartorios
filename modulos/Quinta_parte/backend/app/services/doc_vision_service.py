"""Inspeção prévia de fotos de documentos enviadas pelo cidadão.

1. Pillow: abre a imagem, corrige rotação EXIF e mede resolução e nitidez (rejeita fotos
   pequenas ou borradas antes de gastar uma chamada ao VLM).
2. VLM (Gemini/OpenAI): identifica o tipo do documento, legibilidade e data de emissão.
3. Regra determinística: o prazo de validade (ex.: certidão "atualizada 90 dias") é conferido
   pelo servidor a partir da data lida — o modelo não faz contas de data.

Sem LLM configurado, fotos nítidas ficam como REVISAO_MANUAL (o escrevente confere no painel).
"""

import io
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.schemas.triage_schema import DocumentVerificationResult
from app.services.llm_client import LLMError, active_engine, call_structured

log = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MIN_SIDE_PX = 480
# Desvio-padrão do mapa de bordas (em ~1000 px) abaixo do qual a foto é recusada sem chamar o VLM.
# Conservador: só barra borrão evidente (texto nítido ≈ 40–65; desfoque gaussiano r=3 ≈ 3,6).
MIN_SHARPNESS = 5.0
LLM_MAX_SIDE_PX = 1600


class DocumentError(ValueError):
    pass


@dataclass
class ExpectedDocument:
    doc_name: str
    description: str = ""
    accepted_types: tuple[str, ...] = ()
    max_age_days: Optional[int] = None


@dataclass
class ImageQuality:
    width: int
    height: int
    sharpness: float

    @property
    def too_small(self) -> bool:
        return min(self.width, self.height) < MIN_SIDE_PX

    @property
    def blurry(self) -> bool:
        return self.sharpness < MIN_SHARPNESS


def sniff_content_type(data: bytes) -> Optional[str]:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    return None


def prepare_image(data: bytes) -> tuple[bytes, ImageQuality]:
    """Normaliza a foto (EXIF, RGB, tamanho) e mede a qualidade. Devolve JPEG para o VLM."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise DocumentError("Não foi possível abrir a imagem enviada.") from exc

    gray = img.convert("L")
    # Mede nitidez numa versão de ~1000 px para que o resultado não dependa da resolução da câmera
    probe = gray.copy()
    probe.thumbnail((1000, 1000))
    edges = probe.filter(ImageFilter.FIND_EDGES)
    # Descarta a moldura de 2 px: o filtro marca as bordas da própria imagem como arestas
    edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    sharpness = ImageStat.Stat(edges).stddev[0]
    quality = ImageQuality(img.width, img.height, round(sharpness, 2))

    img.thumbnail((LLM_MAX_SIDE_PX, LLM_MAX_SIDE_PX))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue(), quality


# ---------------------------------------------------------------------------
# Datas e prazo
# ---------------------------------------------------------------------------

_MONTHS = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
           "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def parse_issue_date(text: Optional[str]) -> tuple[Optional[date], bool]:
    """Devolve (data, só_ano). Aceita AAAA-MM-DD, DD/MM/AAAA, "14 de outubro de 2025" ou só o ano."""
    if not text:
        return None, False
    t = text.strip().lower()
    try:
        if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t):
            return date(int(m[1]), int(m[2]), int(m[3])), False
        if m := re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", t):
            return date(int(m[3]), int(m[2]), int(m[1])), False
        if m := re.search(r"(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", t):
            if m[2] in _MONTHS:
                return date(int(m[3]), _MONTHS[m[2]], int(m[1])), False
    except ValueError:
        return None, False
    if m := re.search(r"\b(19|20)\d{2}\b", t):
        return date(int(m[0]), 12, 31), True
    return None, False


def check_age(issue: Optional[str], max_age_days: Optional[int], today: date) -> Optional[str]:
    """Motivo de expiração, ou None se dentro do prazo / sem prazo / data desconhecida."""
    if not max_age_days:
        return None
    issued, year_only = parse_issue_date(issue)
    if issued is None:
        return None
    age = (today - issued).days
    if age <= max_age_days:
        return None
    when = str(issued.year) if year_only else issued.strftime("%d/%m/%Y")
    return f"Documento emitido em {when} — o prazo máximo é de {max_age_days} dias."


# ---------------------------------------------------------------------------
# VLM
# ---------------------------------------------------------------------------

VISION_PROMPT = """Você é um assistente de triagem documental de um cartório brasileiro.
Analise a imagem enviada pelo cidadão e compare com o documento exigido.

Regras:
- is_legible = false se a foto estiver borrada, cortada (faltando partes com dados essenciais), muito escura,
  com reflexo que esconda dados, ou se for uma foto de tela ilegível.
- matches_expected = true somente se o documento for de um dos tipos aceitos.
- issue_date_identified: data de EMISSÃO/EXPEDIÇÃO do documento (não a data do fato registrado, como a data
  do nascimento ou do óbito). Formato AAAA-MM-DD. Se só houver o ano, devolva apenas AAAA. null se não houver.
- validation_status:
  * REJEITADO_ILEGIVEL se não for legível;
  * DOCUMENTO_INCORRETO se for legível mas não for um dos tipos aceitos;
  * EXPIRADO se o próprio documento estiver vencido (ex.: CNH com validade vencida);
  * APROVADO nos demais casos. Não calcule prazos de "atualizada há X dias": o sistema faz isso.
- feedback_to_user: 1 a 2 frases em português simples e acolhedor, sem jargão jurídico, dizendo o que foi
  identificado e, se houver problema, como tirar uma nova foto (boa luz, sem reflexo, documento inteiro).
- Nunca transcreva números de documentos (CPF, RG) no feedback.
"""


async def _verify_with_llm(jpeg: bytes, mime: str, expected: ExpectedDocument, today: date) -> DocumentVerificationResult:
    accepted = ", ".join(expected.accepted_types) or expected.doc_name
    user_text = (
        f"Documento exigido: {expected.doc_name}\n"
        f"Descrição: {expected.description}\n"
        f"Tipos aceitos: {accepted}\n"
        f"Data de hoje: {today.isoformat()}"
    )
    result, used_model = await call_structured(VISION_PROMPT, user_text, DocumentVerificationResult,
                                               media=(jpeg, mime), exclude_fields=frozenset({"engine"}))
    result.engine = used_model
    return result


def _quality_rejection(quality: ImageQuality) -> Optional[DocumentVerificationResult]:
    if quality.too_small:
        reason = "a imagem está muito pequena"
    elif quality.blurry:
        reason = "a foto parece borrada ou tremida"
    else:
        return None
    return DocumentVerificationResult(
        document_type_identified="Não identificado",
        is_legible=False,
        matches_expected=False,
        validation_status="REJEITADO_ILEGIVEL",
        feedback_to_user=(
            f"Não consegui ler o documento porque {reason}. Pode tirar uma nova foto com boa iluminação, "
            "sem reflexo e mostrando o documento inteiro?"
        ),
        engine="quality-check",
    )


async def verify_document(data: bytes, expected: ExpectedDocument,
                          today: Optional[date] = None) -> DocumentVerificationResult:
    today = today or date.today()
    mime = sniff_content_type(data)
    if mime not in ALLOWED_TYPES:
        raise DocumentError("Formato não suportado. Envie uma foto (JPG, PNG ou WEBP) ou um PDF.")

    if mime == "application/pdf":
        payload, payload_mime = data, mime
    else:
        payload, quality = prepare_image(data)
        payload_mime = "image/jpeg"
        if rejection := _quality_rejection(quality):
            log.info("Foto rejeitada no pré-filtro: %s", quality)
            return rejection

    result: Optional[DocumentVerificationResult] = None
    if active_engine() != "heuristic":
        try:
            result = await _verify_with_llm(payload, payload_mime, expected, today)
        except LLMError as exc:
            log.warning("VLM indisponível, documento vai para revisão manual: %s", exc)

    if result is None:
        return DocumentVerificationResult(
            document_type_identified="Não verificado automaticamente",
            is_legible=True,
            matches_expected=True,
            validation_status="REVISAO_MANUAL",
            feedback_to_user=(
                f"Recebi a foto de \"{expected.doc_name}\". Ela será conferida por um de nossos atendentes."
            ),
            engine="heuristic",
        )

    # Prazo de emissão conferido pelo servidor, independentemente do que o modelo disse
    if result.validation_status in ("APROVADO", "EXPIRADO") and expected.max_age_days:
        expired = check_age(result.issue_date_identified, expected.max_age_days, today)
        if expired:
            result.validation_status = "EXPIRADO"
            result.feedback_to_user = (
                f"{expired} Por favor, solicite uma via atualizada no cartório de origem e envie a foto novamente."
            )
        elif parse_issue_date(result.issue_date_identified)[0] is None:
            result.validation_status = "REVISAO_MANUAL"
            result.feedback_to_user = (
                f"Recebi \"{expected.doc_name}\", mas não consegui confirmar a data de emissão. "
                "Um atendente vai conferir se ela está dentro do prazo."
            )
        elif result.validation_status == "EXPIRADO":
            # O modelo achou vencido, mas o prazo de emissão está ok: confere no balcão
            result.validation_status = "REVISAO_MANUAL"
    return result


STATUS_TO_CHECKLIST = {
    "APROVADO": "VALIDADO",
    "REVISAO_MANUAL": "ENVIADO",
    "REJEITADO_ILEGIVEL": "REJEITADO",
    "EXPIRADO": "REJEITADO",
    "DOCUMENTO_INCORRETO": "REJEITADO",
}
