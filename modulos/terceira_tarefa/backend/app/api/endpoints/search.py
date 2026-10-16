from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_collection
from app.schemas.transcription_schema import BookType, HistoricalRecord, RecordStatus, SearchResponse
from app.services import record_service

router = APIRouter(prefix="/api/historical", tags=["busca"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Annotated[str, Query(max_length=200, description="Nome, número de registro, confrontante ou trecho")] = "",
    book_type: Optional[BookType] = None,
    status: Optional[RecordStatus] = None,
    year_from: Annotated[Optional[int], Query(ge=1500, le=2100)] = None,
    year_to: Annotated[Optional[int], Query(ge=1500, le=2100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0)] = 0,
):
    engine, total, items = await record_service.search_records(
        q, book_type=book_type, status=status, year_from=year_from, year_to=year_to, limit=limit, skip=skip
    )
    return {"total": total, "engine": engine, "results": items}


@router.get("/records/{record_id}", response_model=HistoricalRecord)
async def get_record(record_id: str):
    doc = await get_collection().find_one({"_id": record_id}, record_service.SEARCH_PROJECTION_EXCLUDE)
    if doc is None:
        raise HTTPException(404, "Registro não encontrado.")
    return doc
