from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.geo_schema import GeometryAnalysis
from app.services.extractor_service import ExtractionError, extract_memorial
from app.services.geo_calc_service import analyze_geometry

router = APIRouter(prefix="/api/geometry", tags=["geometria"])


@router.post("/analyze", response_model=GeometryAnalysis)
async def analyze(
    memorial: UploadFile = File(..., description="Memorial descritivo (PDF, DOCX ou DOC)"),
    declared_area: Optional[float] = Form(None, description="Área da matrícula (m²) para comparação"),
    utm_zone: Optional[int] = Form(None, ge=18, le=25),
):
    try:
        extraction = await extract_memorial(await memorial.read())
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = analyze_geometry(extraction, declared_area, utm_zone)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail="Memorial sem vértices suficientes (mínimo 3 com coordenadas ou azimute+distância).",
        )
    return result
