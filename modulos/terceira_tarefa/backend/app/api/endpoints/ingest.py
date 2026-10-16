from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import get_collection
from app.schemas.transcription_schema import BookType, HistoricalRecord, RecordUpdate
from app.services import record_service, vlm_service
from app.services.image_service import InvalidImageError, preprocess_historical_image

router = APIRouter(prefix="/api/historical", tags=["ingestão"])

MAX_UPLOAD_BYTES = 40 * 1024 * 1024


@router.post("/transcribe", response_model=HistoricalRecord, status_code=201)
async def transcribe(
    image: Annotated[UploadFile, File(description="Imagem da folha do livro (JPEG, PNG, TIFF)")],
    book_type: Annotated[BookType, Form()],
    book_number: Annotated[str, Form(min_length=1, max_length=20)],
    page_number: Annotated[int, Form(ge=1)],
):
    settings = get_settings()
    raw = await image.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Imagem maior que 40 MB.")

    try:
        processed = await run_in_threadpool(preprocess_historical_image, raw, settings.vlm_image_max_side)
    except InvalidImageError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        result = await vlm_service.transcribe_page(processed.enhanced_jpeg, book_type, book_number, page_number)
    except vlm_service.VLMError as exc:
        raise HTTPException(502, str(exc)) from exc

    record_id = record_service.new_record_id(book_type, book_number, page_number)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / f"{record_id}.jpg").write_bytes(processed.original_jpeg)
    (settings.storage_dir / f"{record_id}_enhanced.jpg").write_bytes(processed.enhanced_jpeg)

    doc = record_service.build_record(
        record_id=record_id,
        book_type=book_type,
        book_number=book_number,
        page_number=page_number,
        image_url=f"{settings.media_url_prefix}/{record_id}.jpg",
        image_enhanced_url=f"{settings.media_url_prefix}/{record_id}_enhanced.jpg",
        result=result,
        vlm_model=settings.vlm_model,
    )
    await get_collection().insert_one(doc)
    return doc


@router.patch("/records/{record_id}", response_model=HistoricalRecord)
async def update_record(record_id: str, payload: RecordUpdate):
    """Correção humana de termos lidos pela IA e homologação (status=verified)."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "Nenhum campo informado.")

    coll = get_collection()
    current = await coll.find_one({"_id": record_id})
    if current is None:
        raise HTTPException(404, "Registro não encontrado.")

    now = datetime.now(timezone.utc)
    if "parties" in changes:
        changes["parties"] = record_service.enrich_parties(changes["parties"])
    if "parties" in changes or "confrontants_or_relatives" in changes:
        changes["search_phonetic"] = record_service.build_search_phonetic(
            changes.get("parties", current["parties"]),
            changes.get("confrontants_or_relatives", current["confrontants_or_relatives"]),
        )
    if changes.get("status") == "verified":
        changes["verified_at"] = now
    elif changes.get("status") == "analyzed":
        changes["verified_at"] = None
    changes["updated_at"] = now

    updated = await coll.find_one_and_update(
        {"_id": record_id}, {"$set": changes}, return_document=True
    )
    return updated
