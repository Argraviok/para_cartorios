from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.core.database import get_repository
from app.schemas.triage_schema import DocumentVerificationResult, UploadDocResponse
from app.services import chat_service
from app.services.chat_service import TriageConflict, TriageNotFound
from app.services.doc_vision_service import DocumentError, ExpectedDocument, verify_document

router = APIRouter(prefix="/api/triage", tags=["documentos"])


async def _read_limited(file: UploadFile) -> bytes:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Arquivo maior que {settings.max_upload_mb} MB.")
    if not data:
        raise HTTPException(422, "Arquivo vazio.")
    return data


@router.post("/upload-doc", response_model=UploadDocResponse)
async def upload_doc(
    protocol_id: str = Form(...),
    file: UploadFile = File(...),
    doc_index: Optional[int] = Form(None, description="Posição no checklist; vazio = próximo pendente"),
):
    """Recebe a foto, valida com o VLM e atualiza o checklist da sessão."""
    data = await _read_limited(file)
    try:
        triage, result, index, replies = await chat_service.handle_upload(protocol_id, data, doc_index)
    except TriageNotFound:
        raise HTTPException(404, "Atendimento não encontrado.")
    except (TriageConflict, DocumentError) as exc:
        raise HTTPException(422, str(exc))
    return UploadDocResponse(triage=triage, verification=result, doc_index=index, replies=replies)


@router.post("/verify-photo", response_model=DocumentVerificationResult)
async def verify_photo(
    expected_doc_type: str = Form(..., description="Nome do documento exigido, ex.: Certidão de Óbito"),
    max_age_days: Optional[int] = Form(None),
    file: UploadFile = File(...),
):
    """Checagem avulsa de uma foto, sem sessão (não grava nada)."""
    data = await _read_limited(file)
    accepted: tuple[str, ...] = ()
    for act in await get_repository().list_requirements():
        for doc in act["documents"]:
            if doc["doc_name"] == expected_doc_type:
                accepted = tuple(doc.get("accepted_types", []))
                max_age_days = max_age_days or doc.get("max_age_days")
    try:
        return await verify_document(
            data, ExpectedDocument(expected_doc_type, accepted_types=accepted or (expected_doc_type,),
                                   max_age_days=max_age_days)
        )
    except DocumentError as exc:
        raise HTTPException(422, str(exc))
