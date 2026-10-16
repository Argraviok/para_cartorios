from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_repository
from app.schemas.triage_schema import (
    AttendantMessageRequest,
    ChecklistReviewRequest,
    StartSessionRequest,
    TakeoverRequest,
    Triage,
    TriageStatus,
    TriageSummary,
    TurnResponse,
    UserMessageRequest,
)
from app.services import chat_service
from app.services.chat_service import TriageConflict, TriageNotFound

router = APIRouter(prefix="/api/triage", tags=["triagem"])


async def _load(protocol_id: str) -> Triage:
    try:
        return await chat_service.load_triage(protocol_id)
    except TriageNotFound:
        raise HTTPException(404, "Atendimento não encontrado.")


@router.post("/sessions", response_model=Triage, status_code=201)
async def start_session(body: StartSessionRequest):
    """Abre um atendimento (widget do cidadão). O bot já envia a saudação."""
    return await chat_service.start_session(body.customer_contact, body.customer_name, body.channel)


@router.post("/message", response_model=TurnResponse)
async def user_message(body: UserMessageRequest):
    """Mensagem do cidadão. Sem protocol_id, retoma o atendimento aberto do contato ou cria um novo."""
    try:
        triage, replies = await chat_service.handle_user_message(
            body.protocol_id, body.message, body.customer_contact, body.customer_name, body.channel
        )
    except TriageNotFound:
        raise HTTPException(404, "Atendimento não encontrado.")
    except TriageConflict as exc:
        raise HTTPException(422, str(exc))
    return TurnResponse(triage=triage, replies=replies)


@router.get("/sessions", response_model=list[TriageSummary])
async def list_sessions(status: Optional[TriageStatus] = None, limit: int = Query(100, ge=1, le=500)):
    """Inbox do escrevente."""
    raws = await get_repository().list_triages(status, limit)
    return [chat_service.summarize(Triage.model_validate(r)) for r in raws]


@router.get("/sessions/{protocol_id}", response_model=Triage)
async def get_session(protocol_id: str):
    return await _load(protocol_id)


@router.post("/sessions/{protocol_id}/takeover", response_model=Triage)
async def takeover(protocol_id: str, body: TakeoverRequest):
    """Transfere para atendimento humano: o bot para de responder."""
    await _load(protocol_id)
    return await chat_service.takeover(protocol_id, body.attendant_name)


@router.post("/sessions/{protocol_id}/release", response_model=Triage)
async def release(protocol_id: str):
    """Devolve o atendimento ao assistente virtual."""
    await _load(protocol_id)
    return await chat_service.release_to_bot(protocol_id)


@router.post("/sessions/{protocol_id}/attendant-message", response_model=Triage)
async def attendant_message(protocol_id: str, body: AttendantMessageRequest):
    await _load(protocol_id)
    return await chat_service.attendant_message(protocol_id, body.message, body.attendant_name)


@router.patch("/sessions/{protocol_id}/checklist/{index}", response_model=Triage)
async def review_checklist(protocol_id: str, index: int, body: ChecklistReviewRequest):
    """Conferência manual de um documento pelo escrevente."""
    await _load(protocol_id)
    try:
        return await chat_service.review_checklist_item(
            protocol_id, index, body.status, body.rejection_reason, body.notify_customer
        )
    except TriageConflict as exc:
        raise HTTPException(422, str(exc))


@router.post("/sessions/{protocol_id}/counter-ticket", response_model=Triage)
async def counter_ticket(protocol_id: str):
    """Gera a senha prioritária de balcão e avisa o cidadão no chat."""
    await _load(protocol_id)
    return await chat_service.issue_counter_ticket(protocol_id)
