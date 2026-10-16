from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import db
from app.schemas.qualification import QualificationResponse
from app.services import ai_service, pdf_service

router = APIRouter(prefix="/api/qualifications", tags=["qualifications"])


# Assinaturas de arquivo: PDF, .docx (zip) e .doc (OLE2).
MAGIC = {".pdf": b"%PDF", ".docx": b"PK\x03\x04", ".doc": b"\xd0\xcf\x11\xe0"}


async def read_upload_as_pdf(file: UploadFile) -> tuple[str, bytes]:
    """Valida o upload e devolve (nome, bytes do PDF), convertendo Word quando necessário."""
    filename = file.filename or "documento.pdf"
    suffix = Path(filename).suffix.lower()
    max_bytes = settings.max_pdf_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if suffix not in MAGIC or not content.startswith(MAGIC[suffix]):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF ou Word (.docx, .doc) são suportados.")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Arquivo excede o limite de {settings.max_pdf_mb} MB.")
    if suffix == ".pdf":
        return filename, content
    try:
        pdf = await run_in_threadpool(
            pdf_service.convert_word_to_pdf, content, suffix, settings.soffice_path
        )
    except pdf_service.ConversionError as exc:
        raise HTTPException(status_code=422, detail=f"Não foi possível converter o documento Word. {exc}")
    return filename, pdf


@router.post("/convert", response_class=Response)
async def convert_document(file: UploadFile = File(...)):
    """Devolve o documento em PDF, para exibição no visualizador."""
    _, pdf = await read_upload_as_pdf(file)
    return Response(content=pdf, media_type="application/pdf")


@router.post("/analyze", response_model=QualificationResponse)
async def analyze_document(
    act_type: str = Form("compra_e_venda_urbano"),
    file: UploadFile = File(...),
):
    filename, content = await read_upload_as_pdf(file)

    try:
        pages = await run_in_threadpool(pdf_service.extract_pages, content)
    except pdf_service.InvalidPDFError:
        raise HTTPException(status_code=400, detail="Não foi possível ler o PDF enviado.")
    if not any(p["text"].strip() for p in pages):
        raise HTTPException(status_code=422, detail="O documento não contém texto extraível (documento digitalizado). OCR não é suportado no MVP.")

    rules = await db["act_rules"].find(
        {"act_type": act_type, "active": {"$ne": False}}
    ).sort("rule_code", 1).to_list(100)
    if not rules:
        raise HTTPException(status_code=404, detail="Regras não cadastradas para este ato.")

    try:
        analysis = await ai_service.analyze(rules, pages)
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=502, detail=f"Falha na análise por IA. {exc}")

    checklist = ai_service.build_checklist(rules, analysis, pages)
    blocking = any(f.status != "CONFORME" and f.severity == "impeditiva" for f in checklist)
    now = datetime.now(timezone.utc)
    record = {
        "document_title": filename,
        "act_type": act_type,
        # O MongoDB guarda datas com precisão de milissegundos.
        "created_at": now.replace(microsecond=now.microsecond // 1000 * 1000),
        "overall_status": "EXIGENCIAS_PENDENTES" if blocking else "APROVADO",
        "checklist": [f.model_dump() for f in checklist],
    }
    inserted = await db["qualifications"].insert_one(record)
    return {**record, "id": str(inserted.inserted_id)}


@router.get("/{qualification_id}", response_model=QualificationResponse)
async def get_qualification(qualification_id: str):
    try:
        oid = ObjectId(qualification_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Qualificação não encontrada.")
    record = await db["qualifications"].find_one({"_id": oid})
    if record is None:
        raise HTTPException(status_code=404, detail="Qualificação não encontrada.")
    return {**record, "id": str(record["_id"])}
