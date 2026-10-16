"""Detecção híbrida (regex + LLM) de dados sensíveis com coordenadas exatas."""

import uuid
from dataclasses import dataclass, field

import pymupdf

from app.core.config import Settings
from app.core.legal_basis import policy_for
from app.schemas.redaction_schema import BoundingBox, PageInfo, RedactionItem
from app.services import llm_client, regex_rules
from app.services.text_layout import PageTextIndex


@dataclass
class _Span:
    page_number: int
    start: int
    end: int
    category: str
    pii_type: str
    source: str


@dataclass
class DetectionResult:
    items: list[RedactionItem]
    pages: list[PageInfo]
    warnings: list[str] = field(default_factory=list)


def _merge_spans(spans: list[_Span]) -> list[_Span]:
    """Une trechos sobrepostos da mesma categoria; o maior trecho prevalece no tipo."""
    spans = sorted(spans, key=lambda s: (s.page_number, s.category, s.start, -s.end))
    merged: list[_Span] = []
    for s in spans:
        last = merged[-1] if merged else None
        if last and last.page_number == s.page_number and last.category == s.category and s.start < last.end:
            if s.end - s.start > last.end - last.start:
                last.pii_type = s.pii_type
            if s.source != last.source:
                last.source = "llm" if "llm" in (s.source, last.source) else last.source
            last.end = max(last.end, s.end)
        else:
            merged.append(_Span(**s.__dict__))
    return sorted(merged, key=lambda s: (s.page_number, s.start))


async def detect_pii(pdf_bytes: bytes, settings: Settings) -> DetectionResult:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        indexes: dict[int, PageTextIndex] = {}
        pages: list[PageInfo] = []
        warnings: list[str] = []
        for page in doc:
            idx = PageTextIndex(page)
            indexes[idx.page_number] = idx
            has_text = bool(idx.text.strip())
            pages.append(PageInfo(page_number=idx.page_number, width=page.rect.width, height=page.rect.height, has_text_layer=has_text))
            if not has_text:
                warnings.append(
                    f"Página {idx.page_number} sem camada de texto (provável digitalização): "
                    "a detecção automática não se aplica — revise e tarje manualmente."
                )

        spans: list[_Span] = []
        for number, idx in indexes.items():
            for m in regex_rules.find_matches(idx.text):
                spans.append(_Span(number, m.start, m.end, m.category, m.pii_type, "regex"))

        if settings.llm_provider != "none":
            try:
                texts = {n: i.text for n, i in indexes.items() if i.text.strip()}
                for f in await llm_client.classify_pages(settings, texts):
                    idx = indexes.get(f.page_number)
                    located = idx.find_phrase(f.text) if idx else []
                    if not located:
                        # O modelo pode errar a página: procura nas demais.
                        for other in indexes.values():
                            if (located := other.find_phrase(f.text)):
                                idx = other
                                break
                    for start, end in located:
                        spans.append(_Span(idx.page_number, start, end, f.category, f.pii_type, "llm"))
            except llm_client.LlmError as exc:
                warnings.append(f"{exc}. Resultado contém apenas a detecção por regras.")

        items: list[RedactionItem] = []
        for s in _merge_spans(spans):
            idx = indexes[s.page_number]
            rects = idx.rects_for_span(s.start, s.end)
            if not rects:
                continue
            policy = policy_for(s.category)
            items.append(
                RedactionItem(
                    redaction_id=f"red_{uuid.uuid4().hex[:10]}",
                    category=s.category,
                    pii_type=s.pii_type,
                    detected_text=idx.text[s.start : s.end].replace("\n", " "),
                    page_number=s.page_number,
                    bboxes=[BoundingBox(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1) for r in rects],
                    approved=policy.approved_by_default,
                    legal_basis=policy.legal_basis,
                    source=s.source,
                )
            )
        return DetectionResult(items=items, pages=pages, warnings=warnings)
    finally:
        doc.close()


def extract_text_in_rects(pdf_bytes: bytes, page_number: int, rects: list[BoundingBox]) -> str:
    """Texto sob as tarjas desenhadas manualmente (exibido ao operador na revisão)."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[page_number - 1]
        parts = [page.get_text("text", clip=pymupdf.Rect(b.x0, b.y0, b.x1, b.y1)).strip() for b in rects]
        return " ".join(p for p in parts if p)
