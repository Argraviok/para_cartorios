import uuid
from datetime import datetime, timezone

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.core.config import Settings, get_settings
from app.core.database import Repository, get_repository
from app.core.legal_basis import MANUAL_LEGAL_BASIS
from app.schemas.redaction_schema import JobSummary, RedactionItem, RedactionJob, ReviewUpdateRequest, ServiceType
from app.services import audit_service, storage
from app.services.document_converter import ConversionError, convert_to_pdf, detect_format
from app.services.pii_detector_service import detect_pii, extract_text_in_rects

router = APIRouter(prefix="/api/redact", tags=["análise"])


async def load_job(repo: Repository, job_id: str) -> RedactionJob:
    data = await repo.get_job(job_id)
    if not data:
        raise HTTPException(404, "Job não encontrado")
    return RedactionJob.model_validate(data)


def normalize_items(items: list[RedactionItem], original: bytes, page_count: int) -> list[RedactionItem]:
    """Valida páginas e completa, no servidor, os campos das tarjas manuais."""
    result = []
    for item in items:
        if item.page_number > page_count:
            raise HTTPException(422, f"{item.redaction_id}: página {item.page_number} inexistente")
        if item.source == "manual":
            item = item.model_copy(
                update={
                    "detected_text": extract_text_in_rects(original, item.page_number, item.bboxes),
                    "legal_basis": MANUAL_LEGAL_BASIS,
                }
            )
        result.append(item)
    return result


@router.post("/analyze", response_model=RedactionJob)
async def analyze(
    file: UploadFile = File(...),
    service_type: ServiceType = Form("registro_civil"),
    operator: str = Form("sistema", max_length=120),
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> RedactionJob:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Arquivo excede {settings.max_upload_mb} MB")
    source_format = detect_format(data)
    if source_format is None:
        raise HTTPException(415, "Formato não suportado: envie PDF, DOCX ou DOC")
    source = data
    if source_format != "pdf":
        try:
            data = await run_in_threadpool(convert_to_pdf, source, source_format, settings)
        except ConversionError as exc:
            raise HTTPException(422, str(exc)) from exc
    try:
        with pymupdf.open(stream=data, filetype="pdf") as probe:
            encrypted, page_count = probe.needs_pass, probe.page_count
    except Exception as exc:
        raise HTTPException(422, "Documento corrompido ou ilegível") from exc
    if encrypted:
        raise HTTPException(422, "Documento protegido por senha: remova a proteção antes do envio")
    if page_count == 0:
        raise HTTPException(422, "Documento sem páginas")

    detection = await detect_pii(data, settings)
    job_id = f"job_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)
    job = RedactionJob(
        job_id=job_id,
        filename=file.filename or "documento.pdf",
        service_type=service_type,
        status="pending_review" if detection.items else "analyzed",
        total_detected=len(detection.items),
        items=detection.items,
        pages=detection.pages,
        warnings=detection.warnings,
        llm_provider=settings.llm_provider,
        source_format=source_format,
        source_sha256=storage.sha256(source) if source_format != "pdf" else None,
        original_sha256=storage.sha256(data),
        created_at=now,
        updated_at=now,
    )
    if source_format != "pdf":
        await run_in_threadpool(storage.save_source, job_id, source, source_format)
    await run_in_threadpool(storage.save_original, job_id, data)
    await repo.insert_job(job.model_dump())
    await audit_service.record(repo, job, "ANALYZE", operator, job.items)
    return job


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(limit: int = Query(50, ge=1, le=500), repo: Repository = Depends(get_repository)):
    return [JobSummary.model_validate(j) for j in await repo.list_jobs(limit)]


@router.get("/jobs/{job_id}", response_model=RedactionJob)
async def get_job(job_id: str, repo: Repository = Depends(get_repository)) -> RedactionJob:
    return await load_job(repo, job_id)


@router.put("/jobs/{job_id}/items", response_model=RedactionJob)
async def save_review(job_id: str, body: ReviewUpdateRequest, repo: Repository = Depends(get_repository)) -> RedactionJob:
    job = await load_job(repo, job_id)
    if job.status == "sanitized":
        raise HTTPException(409, "Documento já sanitizado")
    original = await run_in_threadpool(storage.read_original, job_id)
    items = await run_in_threadpool(normalize_items, body.items, original, len(job.pages))
    job.items = items
    job.status = "pending_review"
    job.updated_at = datetime.now(timezone.utc)
    await repo.update_job(job_id, {"items": [i.model_dump() for i in items], "status": job.status, "updated_at": job.updated_at})
    await audit_service.record(repo, job, "REVIEW_SAVED", body.operator, items)
    return job


def _render_page(job_id: str, page_number: int, scale: float) -> bytes:
    with pymupdf.open(storage.original_path(job_id)) as doc:
        if not 1 <= page_number <= doc.page_count:
            raise HTTPException(404, "Página inexistente")
        pix = doc[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(scale, scale), annots=False)
        return pix.tobytes("png")


@router.get("/jobs/{job_id}/pages/{page_number}.png")
async def page_image(
    job_id: str,
    page_number: int,
    scale: float = Query(1.5, ge=0.5, le=4),
    repo: Repository = Depends(get_repository),
) -> Response:
    await load_job(repo, job_id)
    png = await run_in_threadpool(_render_page, job_id, page_number, scale)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, no-store"})
