from datetime import datetime, timezone
from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.api.endpoints.redact_analysis import load_job, normalize_items
from app.core.config import Settings, get_settings
from app.core.database import Repository, get_repository
from app.schemas.redaction_schema import ApplyRequest, AuditLogEntry, RedactionItem
from app.services import audit_service, storage
from app.services.pdf_sanitizer_service import SanitizationError, sanitize

router = APIRouter(prefix="/api/redact", tags=["tarjamento"])


def _sanitized_name(filename: str) -> str:
    return f"{PurePath(filename).stem}_tarjado.pdf"


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
        },
    )


def _purge(items: list[RedactionItem]) -> list[RedactionItem]:
    return [
        i.model_copy(update={"detected_text": f"[conteúdo removido após sanitização · {len(i.detected_text)} caracteres]"})
        for i in items
    ]


@router.post("/apply")
async def apply(
    body: ApplyRequest,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not body.confirm_irreversible:
        raise HTTPException(422, "Confirme que a operação é irreversível no documento gerado")
    job = await load_job(repo, body.job_id)
    if job.status == "sanitized":
        raise HTTPException(409, "Documento já sanitizado: baixe o arquivo existente")

    original = await run_in_threadpool(storage.read_original, job.job_id)
    if storage.sha256(original) != job.original_sha256:
        raise HTTPException(500, "Integridade do original comprometida (hash divergente)")
    items = await run_in_threadpool(normalize_items, body.items, original, len(job.pages))

    try:
        output = await run_in_threadpool(sanitize, original, items)
    except SanitizationError as exc:
        raise HTTPException(500, str(exc)) from exc

    await run_in_threadpool(storage.save_sanitized, job.job_id, output)
    now = datetime.now(timezone.utc)
    job.items = items
    job.status = "sanitized"
    job.sanitized_sha256 = storage.sha256(output)
    job.sanitized_at = now
    job.sanitized_by = body.operator
    job.updated_at = now
    await audit_service.record(repo, job, "SANITIZE", body.operator, items)

    stored_items = _purge(items) if settings.purge_detected_text_on_finalize else items
    await repo.update_job(
        job.job_id,
        {
            "items": [i.model_dump() for i in stored_items],
            "status": job.status,
            "total_detected": len(items),
            "sanitized_sha256": job.sanitized_sha256,
            "sanitized_at": now,
            "sanitized_by": body.operator,
            "updated_at": now,
        },
    )
    return _pdf_response(output, _sanitized_name(job.filename))


@router.get("/jobs/{job_id}/sanitized")
async def download_sanitized(job_id: str, repo: Repository = Depends(get_repository)) -> Response:
    job = await load_job(repo, job_id)
    if job.status != "sanitized":
        raise HTTPException(409, "Documento ainda não sanitizado")
    data = await run_in_threadpool(storage.read_sanitized, job_id)
    return _pdf_response(data, _sanitized_name(job.filename))


@router.get("/jobs/{job_id}/audit", response_model=list[AuditLogEntry])
async def audit_entries(job_id: str, repo: Repository = Depends(get_repository)) -> list[AuditLogEntry]:
    await load_job(repo, job_id)
    return [AuditLogEntry.model_validate(e) for e in await repo.list_audit(job_id)]


@router.get("/jobs/{job_id}/audit.csv")
async def audit_csv(job_id: str, repo: Repository = Depends(get_repository)) -> Response:
    entries = await audit_entries(job_id, repo)
    return Response(
        audit_service.to_csv(entries),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="auditoria_{job_id}.csv"'},
    )


@router.get("/jobs/{job_id}/audit.pdf")
async def audit_pdf(job_id: str, repo: Repository = Depends(get_repository)) -> Response:
    job = await load_job(repo, job_id)
    entries = [AuditLogEntry.model_validate(e) for e in await repo.list_audit(job_id)]
    data = await run_in_threadpool(audit_service.to_pdf, job, entries)
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="auditoria_{job_id}.pdf"'},
    )
