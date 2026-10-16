from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.geo_schema import SubjectiveContinuity
from app.services.continuity_service import analyze_continuity
from app.services.extractor_service import ExtractionError, extract_registry, extract_title

router = APIRouter(prefix="/api/continuity", tags=["continuidade dominial"])


async def resolve_sellers(titulo: Optional[UploadFile], seller_name: Optional[str]) -> list[str]:
    """Vendedor informado manualmente tem precedência sobre o extraído do título."""
    if seller_name and seller_name.strip():
        return [s.strip() for s in seller_name.split(";") if s.strip()]
    if titulo is not None:
        return (await extract_title(await titulo.read())).sellers
    return []


@router.post("/analyze", response_model=SubjectiveContinuity)
async def analyze(
    matricula: UploadFile = File(..., description="Certidão de matrícula (PDF, DOCX ou DOC)"),
    titulo: Optional[UploadFile] = File(None, description="Título/contrato apresentado (PDF, DOCX ou DOC)"),
    seller_name: Optional[str] = Form(None, description="Vendedor(es), separados por ';'"),
):
    try:
        registry = await extract_registry(await matricula.read())
        sellers = await resolve_sellers(titulo, seller_name)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return analyze_continuity(registry, sellers)
