"""Tarjamento destrutivo no binário do PDF e verificação obrigatória do resultado."""

import pymupdf

from app.schemas.redaction_schema import RedactionItem


class SanitizationError(Exception):
    pass


def _rects(item: RedactionItem, page: pymupdf.Page) -> list[pymupdf.Rect]:
    rects = []
    for b in item.bboxes:
        r = pymupdf.Rect(b.x0, b.y0, b.x1, b.y1) & page.rect
        if not r.is_empty:
            rects.append(r)
    return rects


def apply_real_redactions(pdf_bytes: bytes, items: list[RedactionItem]) -> bytes:
    """Executa a sanitização binária real do PDF (redação destrutiva).

    - Texto sob a tarja é removido do content stream (não apenas coberto).
    - Pixels de imagens sob a tarja são apagados (cobre páginas digitalizadas).
    - Vetores que tocam a tarja são removidos (glifos desenhados como curvas).
    - Anotações sobrepostas, metadados, anexos, JavaScript e miniaturas são eliminados.
    - O arquivo é regravado por completo (garbage=4), sem objetos órfãos com o conteúdo antigo.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.needs_pass:
            raise SanitizationError("PDF protegido por senha")

        by_page: dict[int, list[pymupdf.Rect]] = {}
        for item in items:
            if not item.approved:
                continue
            if item.page_number > doc.page_count:
                raise SanitizationError(f"Página {item.page_number} inexistente no documento")
            page = doc[item.page_number - 1]
            by_page.setdefault(item.page_number, []).extend(_rects(item, page))

        for page_number, rects in by_page.items():
            page = doc[page_number - 1]
            # Anotações (notas, FreeText, carimbos) sobre a área tarjada carregariam o dado consigo.
            for annot in list(page.annots() or []):
                if any(annot.rect.intersects(r) for r in rects):
                    page.delete_annot(annot)
            for r in rects:
                page.add_redact_annot(r, fill=(0, 0, 0), cross_out=False)  # tarja preta opaca
            page.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                text=pymupdf.PDF_REDACT_TEXT_REMOVE,
            )

        doc.scrub(
            attached_files=True,
            embedded_files=True,
            javascript=True,
            metadata=True,
            xml_metadata=True,
            thumbnails=True,
            reset_responses=True,
            remove_links=True,
            reset_fields=True,
            clean_pages=True,
            hidden_text=False,  # o texto oculto sob as tarjas já foi removido acima
            redactions=False,
        )
        return doc.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def verify_sanitization(output_bytes: bytes, items: list[RedactionItem]) -> list[str]:
    """Teste de seleção de texto: nenhuma palavra pode ser extraível sob uma tarja aprovada.

    Retorna a lista de problemas; vazia significa documento aprovado.
    """
    problems: list[str] = []
    with pymupdf.open(stream=output_bytes, filetype="pdf") as doc:
        for page in doc:
            if any(a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in page.annots() or []):
                problems.append(f"Página {page.number + 1}: anotação de redação não aplicada")
        for item in items:
            if not item.approved:
                continue
            page = doc[item.page_number - 1]
            for r in _rects(item, page):
                for w in page.get_text("words", clip=r + (-1, -1, 1, 1)):
                    center = pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
                    if center in r:
                        problems.append(f"{item.redaction_id}: texto ainda extraível na página {item.page_number}")
                        break
        if doc.metadata and any(v for k, v in doc.metadata.items() if k not in ("format", "encryption")):
            problems.append("Metadados do documento não foram removidos")
    return problems


def sanitize(pdf_bytes: bytes, items: list[RedactionItem]) -> bytes:
    output = apply_real_redactions(pdf_bytes, items)
    problems = verify_sanitization(output, items)
    if problems:
        raise SanitizationError("Verificação pós-tarja falhou: " + "; ".join(problems))
    return output
