from fastapi import HTTPException, Request

from app.core.config import Settings, get_settings
from app.repositories.notes import NoteRepository
from app.repositories.precedents import PrecedentRepository
from app.services.embedding_service import Embedder
from app.services.generator_service import NoteGenerator


def settings_dep() -> Settings:
    return get_settings()


def note_repo_dep(request: Request) -> NoteRepository:
    return request.app.state.note_repo


def precedent_repo_dep(request: Request) -> PrecedentRepository:
    return request.app.state.precedent_repo


def generator_dep(request: Request) -> NoteGenerator:
    return request.app.state.generator


def embedder_dep(request: Request) -> Embedder:
    embedder = request.app.state.embedder
    if embedder is None:
        raise HTTPException(503, "Serviço de embeddings não configurado (verifique a chave de API).")
    return embedder
