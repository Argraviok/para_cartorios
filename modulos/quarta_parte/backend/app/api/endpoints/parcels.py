"""Fluxo completo: matrícula + memorial (+ título) → análise dominial e topográfica persistida."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.endpoints.analyze_continuity import resolve_sellers
from app.core.config import settings
from app.core.database import get_repository
from app.schemas.geo_schema import (
    Alert,
    ApproximateLocation,
    GeometryAnalysis,
    MemorialExtraction,
    ParcelAnalysis,
    RegistryExtraction,
    SubjectiveContinuity,
)
from app.services.continuity_service import analyze_continuity
from app.services.extractor_service import (
    ExtractionError,
    active_engine,
    extract_memorial,
    extract_registry,
)
from app.services.geo_calc_service import analyze_geometry, distance_m, fmt_br, geometry_center, zone_from_lon
from app.services.geocoding_service import geocode_address

router = APIRouter(prefix="/api/parcels", tags=["análise completa"])


def build_alerts(cont: SubjectiveContinuity, geo: Optional[GeometryAnalysis], had_memorial: bool) -> list[Alert]:
    alerts: list[Alert] = []
    if cont.status == "QUEBRA_DETECTADA":
        alerts.append(Alert(level="CRITICAL", code="QUEBRA_CONTINUIDADE", message=cont.observation))
    for lien in cont.active_liens:
        level = "CRITICAL" if lien.type in ("INDISPONIBILIDADE", "PENHORA", "ARRESTO") else "WARNING"
        alerts.append(Alert(level=level, code=f"ONUS_{lien.type}", message=f"{lien.type} vigente ({lien.act_code}): {lien.summary}"))

    if had_memorial and geo is None:
        alerts.append(Alert(level="WARNING", code="MEMORIAL_SEM_VERTICES",
                            message="Não foi possível reconstruir o perímetro a partir do memorial."))
    if geo is None:
        return alerts

    if not geo.is_closed:
        alerts.append(Alert(level="CRITICAL", code="PERIMETRO_NAO_FECHA",
                            message=f"Perímetro não fecha: erro de fechamento de {fmt_br(geo.gap_meters, 3)} m."))
    elif geo.gap_meters > settings.closure_tolerance_m:
        alerts.append(Alert(level="INFO", code="FECHAMENTO_TOLERAVEL",
                            message=f"Erro de fechamento de {fmt_br(geo.gap_meters, 3)} m (dentro da tolerância)."))
    if geo.area_difference_percent is not None and geo.area_difference_percent > settings.area_tolerance_percent:
        alerts.append(Alert(
            level="CRITICAL", code="DIVERGENCIA_AREA",
            message=f"Área calculada ({fmt_br(geo.calculated_area)} m²) diverge {fmt_br(geo.area_difference_percent)}% "
                    f"da área declarada ({fmt_br(geo.declared_area)} m²) — acima do limite de "
                    f"{settings.area_tolerance_percent:.0f}%."))
    if not geo.is_valid_polygon:
        alerts.append(Alert(level="CRITICAL", code="POLIGONO_INVALIDO",
                            message="Polígono com auto-interseção: ordem dos vértices inconsistente."))
    for w in geo.warnings:
        alerts.append(Alert(level="WARNING", code="GEOMETRIA", message=w))
    registries = [c for c in geo.confrontants if c.registry]
    if registries:
        alerts.append(Alert(
            level="INFO", code="CONFRONTANTES_MATRICULADOS",
            message="Validar confrontações com as matrículas vizinhas: "
                    + ", ".join(f"{c.registry} ({c.segment})" for c in registries) + "."))
    return alerts


DISTANCE_LIMIT_M = {"ENDERECO": 1_000, "RUA": 3_000, "BAIRRO": 5_000, "CIDADE": 40_000}


def pick_geometry_input(
    memorial_ext: Optional[MemorialExtraction], registry: RegistryExtraction
) -> tuple[Optional[MemorialExtraction], str]:
    """Memorial tem prioridade; sem ele (ou sem vértices nele), usa a descrição da própria matrícula."""
    if memorial_ext and len(memorial_ext.vertices) >= 3:
        return memorial_ext, "MEMORIAL"
    if len(registry.vertices) >= 3:
        return MemorialExtraction(
            declared_area_m2=registry.declared_area_m2,
            utm_zone=registry.utm_zone,
            datum=registry.datum,
            vertices=registry.vertices,
        ), "MATRICULA"
    return memorial_ext, "MEMORIAL"


async def complete_alerts(
    continuity: SubjectiveContinuity,
    geometry: Optional[GeometryAnalysis],
    location: Optional[ApproximateLocation],
    had_memorial: bool,
    registry_number: str,
) -> list[Alert]:
    alerts = build_alerts(continuity, geometry, had_memorial)

    if geometry and geometry.source == "MATRICULA":
        alerts.append(Alert(level="INFO", code="GEOMETRIA_DA_MATRICULA",
                            message="Perímetro extraído da descrição da própria matrícula."))
    if location and geometry and geometry.georeference_method == "COORDINATES":
        center = geometry_center(geometry)
        if center:
            dist = distance_m(center, (location.lat, location.lon))
            if dist > DISTANCE_LIMIT_M[location.precision]:
                alerts.append(Alert(
                    level="CRITICAL", code="COORDENADAS_LONGE_DO_ENDERECO",
                    message=f"O polígono está a {fmt_br(dist / 1000, 1)} km do endereço da matrícula "
                            f"({location.query}). Verifique fuso UTM, datum e dígitos das coordenadas."))
    elif location and (geometry is None or not geometry.is_georeferenced):
        alerts.append(Alert(level="INFO", code="LOCALIZACAO_APROXIMADA",
                            message=f"Localização aproximada pelo endereço (precisão: {location.precision.lower()}). "
                                    "Não substitui o georreferenciamento do perímetro."))

    if geometry and geometry.location_geojson:
        for other in await get_repository().find_overlaps(geometry.location_geojson, registry_number):
            alerts.append(Alert(level="CRITICAL", code="SOBREPOSICAO",
                                message=f"Polígono intersecta imóvel já analisado: matrícula {other['registry_number']}."))
    return alerts


@router.post("/analyze", response_model=ParcelAnalysis)
async def analyze_parcel(
    matricula: UploadFile = File(..., description="Certidão de matrícula (PDF, DOCX ou DOC)"),
    memorial: Optional[UploadFile] = File(None, description="Memorial descritivo (PDF, DOCX ou DOC)"),
    titulo: Optional[UploadFile] = File(None, description="Título/contrato apresentado (PDF, DOCX ou DOC)"),
    seller_name: Optional[str] = Form(None, description="Vendedor(es) no título, separados por ';'"),
    utm_zone: Optional[int] = Form(None, ge=18, le=25),
):
    matricula_bytes = await matricula.read()
    memorial_bytes = await memorial.read() if memorial else None
    try:
        registry, memorial_ext, sellers = await asyncio.gather(
            extract_registry(matricula_bytes),
            extract_memorial(memorial_bytes) if memorial_bytes else asyncio.sleep(0, None),
            resolve_sellers(titulo, seller_name),
        )
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    continuity = analyze_continuity(registry, sellers)
    location = await geocode_address(registry.property_address)
    geometry_input, source = pick_geometry_input(memorial_ext, registry)
    geometry = (
        analyze_geometry(
            geometry_input, registry.declared_area_m2, utm_zone,
            inferred_zone=zone_from_lon(location.lon) if location else None,
            source=source,
        )
        if geometry_input
        else None
    )
    alerts = await complete_alerts(continuity, geometry, location, memorial_bytes is not None, registry.registry_number)

    analysis = ParcelAnalysis(
        registry_number=registry.registry_number,
        registry_office=registry.registry_office,
        document_filename=matricula.filename or "matricula.pdf",
        memorial_filename=memorial.filename if memorial else None,
        subjective_continuity=continuity,
        geometry=geometry,
        approximate_location=location,
        property_address=registry.property_address,
        registry_declared_area=registry.declared_area_m2,
        geometry_input=geometry_input,
        alerts=alerts,
        extraction_engine=active_engine(),
        created_at=datetime.now(timezone.utc),
    )
    analysis.id = await get_repository().insert(analysis.model_dump(exclude={"id"}))
    return analysis


class AnchorRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


@router.post("/{analysis_id}/anchor", response_model=ParcelAnalysis)
async def anchor_parcel(analysis_id: str, body: AnchorRequest):
    """Posiciona no mapa um perímetro sem coordenadas, a partir do primeiro vértice clicado pelo usuário."""
    repo = get_repository()
    doc = await repo.get(analysis_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    analysis = ParcelAnalysis.model_validate(doc)
    if analysis.geometry is None or analysis.geometry_input is None:
        raise HTTPException(status_code=409, detail="Esta análise não tem perímetro para posicionar.")
    if analysis.geometry.georeference_method == "COORDINATES":
        raise HTTPException(status_code=409, detail="O perímetro já é georreferenciado por coordenadas.")

    geometry = analyze_geometry(
        analysis.geometry_input, analysis.registry_declared_area,
        anchor=(body.lat, body.lon), source=analysis.geometry.source,
    )
    if geometry is None or not geometry.is_georeferenced:
        raise HTTPException(status_code=422, detail="Perímetro sem azimutes e distâncias completos: não é possível posicioná-lo.")
    analysis.geometry = geometry
    analysis.alerts = await complete_alerts(
        analysis.subjective_continuity, geometry, analysis.approximate_location,
        analysis.memorial_filename is not None, analysis.registry_number,
    )
    await repo.update(analysis_id, {"geometry": geometry.model_dump(), "alerts": [a.model_dump() for a in analysis.alerts]})
    return analysis


@router.get("", response_model=list[dict])
async def list_parcels(limit: int = Query(20, ge=1, le=100)):
    return await get_repository().list_recent(limit)


@router.get("/{analysis_id}", response_model=ParcelAnalysis)
async def get_parcel(analysis_id: str):
    doc = await get_repository().get(analysis_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    return doc
