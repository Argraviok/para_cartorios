from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.enums import VICIO_LABELS

router = APIRouter(prefix="/api/vicios", tags=["vicios"])


class VicioOut(BaseModel):
    code: str
    label: str


@router.get("", response_model=list[VicioOut])
async def list_vicios():
    return [VicioOut(code=code.value, label=label) for code, label in VICIO_LABELS.items()]
