from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.api.deps import parse_object_id, read_upload
from app.core import storage
from app.core.database import get_db
from app.schemas.fraud_schema import SignatureCard, SignatureCardCreate
from app.services.cpf import format_cpf, is_valid_cpf
from app.services.signature_service import InvalidSignatureImage, crop_signature_png

router = APIRouter(prefix="/api/signature-cards", tags=["Cartões de firma"])


def to_card(doc: dict) -> SignatureCard:
    return SignatureCard(id=str(doc["_id"]), cpf=doc["cpf"], full_name=doc["full_name"],
                         card_number=doc.get("card_number"), created_at=doc["created_at"])


@router.post("", response_model=SignatureCard, status_code=status.HTTP_201_CREATED)
async def create_card(
    cpf: str = Form(...),
    full_name: str = Form(...),
    card_number: str | None = Form(None),
    signature: UploadFile = File(..., description="Imagem do padrão gráfico (ficha de firma)"),
):
    try:
        payload = SignatureCardCreate(cpf=cpf, full_name=full_name, card_number=card_number)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors(include_url=False, include_context=False)) from None
    data = await read_upload(signature, "Assinatura")
    try:
        cropped = crop_signature_png(data)
    except InvalidSignatureImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    key = storage.save(cropped, "signature_cards", ".png")
    doc = {**payload.model_dump(), "signature_sample_url": key, "created_at": datetime.now(timezone.utc)}
    try:
        result = await get_db().signature_cards.insert_one(doc)
    except DuplicateKeyError:
        storage.delete(key)
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe cartão de firma para este CPF") from None
    doc["_id"] = result.inserted_id
    return to_card(doc)


@router.get("", response_model=list[SignatureCard])
async def list_cards(q: str | None = None, limit: int = 50):
    query: dict = {}
    if q:
        if is_valid_cpf(q):
            query = {"cpf": format_cpf(q)}
        else:
            query = {"full_name": {"$regex": q.strip()[:60].replace("\\", ""), "$options": "i"}}
    cursor = get_db().signature_cards.find(query).sort("full_name", 1).limit(min(limit, 200))
    return [to_card(d) async for d in cursor]


@router.get("/by-cpf/{cpf}", response_model=SignatureCard)
async def get_by_cpf(cpf: str):
    if not is_valid_cpf(cpf):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "CPF inválido")
    doc = await get_db().signature_cards.find_one({"cpf": format_cpf(cpf)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cartão de firma não encontrado")
    return to_card(doc)


@router.get("/{card_id}/image")
async def card_image(card_id: str):
    doc = await get_db().signature_cards.find_one({"_id": parse_object_id(card_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cartão de firma não encontrado")
    key = doc["signature_sample_url"]
    return Response(storage.load(key), media_type=storage.media_type(key), headers={"Cache-Control": "no-store"})
