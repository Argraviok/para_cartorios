"""Logs de auditoria LGPD e relatórios (CSV/PDF). Nunca registra o conteúdo tarjado."""

import csv
import html
import io
import uuid
from collections import Counter
from datetime import datetime, timezone

import pymupdf

from app.core.database import Repository
from app.core.legal_basis import CATEGORY_POLICIES
from app.schemas.redaction_schema import AuditLogEntry, RedactionItem, RedactionJob


async def record(
    repo: Repository,
    job: RedactionJob,
    event: str,
    operator: str,
    items: list[RedactionItem],
) -> AuditLogEntry:
    approved = [i for i in items if i.approved]
    entry = AuditLogEntry(
        audit_id=uuid.uuid4().hex,
        job_id=job.job_id,
        event=event,
        operator=operator,
        timestamp=datetime.now(timezone.utc),
        filename=job.filename,
        service_type=job.service_type,
        categories=dict(Counter(i.category for i in approved)),
        approved_count=len(approved),
        rejected_count=len(items) - len(approved),
        manual_count=sum(1 for i in items if i.source == "manual"),
        legal_bases=sorted({i.legal_basis for i in approved}),
        original_sha256=job.original_sha256,
        sanitized_sha256=job.sanitized_sha256,
        llm_provider=job.llm_provider,
    )
    await repo.insert_audit(entry.model_dump())
    return entry


_CSV_FIELDS = [
    "timestamp", "event", "operator", "job_id", "filename", "service_type", "approved_count",
    "rejected_count", "manual_count", "categories", "legal_bases", "original_sha256", "sanitized_sha256",
]


def to_csv(entries: list[AuditLogEntry]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, delimiter=";")
    writer.writeheader()
    for e in entries:
        row = e.model_dump()
        row["timestamp"] = e.timestamp.isoformat()
        row["categories"] = ", ".join(f"{k}={v}" for k, v in e.categories.items())
        row["legal_bases"] = " | ".join(e.legal_bases)
        writer.writerow({k: row[k] for k in _CSV_FIELDS})
    return "﻿" + buf.getvalue()  # BOM para abrir corretamente no Excel


def to_pdf(job: RedactionJob, entries: list[AuditLogEntry]) -> bytes:
    esc = html.escape
    approved = [i for i in job.items if i.approved]
    by_cat = Counter(i.category for i in approved)
    cat_rows = "".join(
        f"<tr><td>{esc(CATEGORY_POLICIES[c].label)}</td><td>{n}</td><td>{esc(CATEGORY_POLICIES[c].legal_basis)}</td></tr>"
        for c, n in sorted(by_cat.items())
    )
    manual = sum(1 for i in approved if i.source == "manual")
    if manual:
        cat_rows += f"<tr><td>Tarjas manuais</td><td>{manual}</td><td>Decisão do operador</td></tr>"
    log_rows = "".join(
        f"<tr><td>{e.timestamp:%d/%m/%Y %H:%M:%S} UTC</td><td>{esc(e.event)}</td><td>{esc(e.operator)}</td>"
        f"<td>{e.approved_count} aprovadas / {e.rejected_count} rejeitadas</td></tr>"
        for e in entries
    )
    body = f"""
    <h1>Relatório de Auditoria LGPD — Tarjamento</h1>
    <p><b>Documento:</b> {esc(job.filename)}<br>
    <b>Job:</b> {esc(job.job_id)}<br>
    <b>Serventia / serviço:</b> {esc(job.service_type)}<br>
    <b>Status:</b> {esc(job.status)}<br>
    <b>Sanitizado em:</b> {f"{job.sanitized_at:%d/%m/%Y %H:%M:%S} UTC por {esc(job.sanitized_by or '')}" if job.sanitized_at else "—"}<br>
    {f'<b>Documento enviado:</b> Word (.{job.source_format}), convertido para PDF antes do tarjamento<br><b>SHA-256 do Word enviado:</b> <span class="mono">{job.source_sha256}</span><br>' if job.source_format != "pdf" else ""}
    <b>SHA-256 original (PDF):</b> <span class="mono">{job.original_sha256}</span><br>
    <b>SHA-256 sanitizado:</b> <span class="mono">{job.sanitized_sha256 or "—"}</span></p>
    <h2>Tarjas aplicadas por categoria</h2>
    <table><tr><th>Categoria</th><th>Qtd.</th><th>Fundamentação</th></tr>{cat_rows or '<tr><td colspan="3">Nenhuma</td></tr>'}</table>
    <h2>Trilha de auditoria</h2>
    <table><tr><th>Data/hora</th><th>Evento</th><th>Operador</th><th>Resumo</th></tr>{log_rows}</table>
    <p class="note">Este relatório não reproduz o conteúdo tarjado. O arquivo sanitizado passou pelo teste
    automático de extração de texto sob as tarjas (nenhum texto selecionável remanescente).</p>
    """
    css = """
    * { font-family: sans-serif; font-size: 9pt; }
    h1 { font-size: 14pt; } h2 { font-size: 11pt; margin-top: 12pt; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 0.5pt solid #888; padding: 3pt; text-align: left; vertical-align: top; }
    th { background: #eee; } .mono { font-family: monospace; font-size: 7pt; } .note { color: #555; font-size: 8pt; }
    """
    story = pymupdf.Story(html=body, user_css=css)
    writer_buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(writer_buf)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (40, 40, -40, -40)
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return writer_buf.getvalue()
