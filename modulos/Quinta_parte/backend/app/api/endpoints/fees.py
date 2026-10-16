from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.database import get_repository
from app.schemas.triage_schema import ActRequirement, FeeEstimateResult
from app.services.fee_calculator_service import FeeError, estimate_for_act

router = APIRouter(prefix="/api", tags=["emolumentos"])


@router.get("/acts", response_model=list[ActRequirement])
async def list_acts():
    """Atos atendidos e documentos exigidos (coleção act_requirements)."""
    return await get_repository().list_requirements()


@router.get("/fees/schedules")
async def list_schedules(state: Optional[str] = None):
    return await get_repository().list_fee_schedules(state)


@router.get("/fees/estimate", response_model=FeeEstimateResult)
async def estimate(act_type: str, declared_value: Optional[float] = Query(None, ge=0),
                   state: str = settings.office_state):
    requirement = await get_repository().get_requirement(act_type)
    if requirement is None:
        raise HTTPException(404, "Ato não cadastrado.")
    try:
        return await estimate_for_act(requirement, state, declared_value)
    except FeeError as exc:
        raise HTTPException(422, str(exc))
