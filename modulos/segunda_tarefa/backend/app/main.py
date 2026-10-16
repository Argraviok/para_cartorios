import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import devolution, precedents, vicios
from app.core.config import get_settings
from app.core.database import create_client, get_database
from app.repositories.notes import MongoNoteRepository
from app.repositories.precedents import MongoPrecedentRepository
from app.services.embedding_service import build_embedder
from app.services.generator_service import NoteGenerator
from app.services.llm_service import build_llm
from app.services.search_service import MongoHybridSearcher

log = logging.getLogger("uvicorn.error")


def _optional(factory, name: str):
    try:
        return factory()
    except RuntimeError as exc:
        log.warning("%s desativado: %s", name, exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    client = create_client(settings)
    db = get_database(client, settings)

    embedder = _optional(lambda: build_embedder(settings), "Embeddings")
    llm = _optional(lambda: build_llm(settings), "LLM")

    app.state.embedder = embedder
    app.state.note_repo = MongoNoteRepository(db)
    app.state.precedent_repo = MongoPrecedentRepository(db)
    app.state.generator = NoteGenerator(MongoHybridSearcher(db, embedder), llm, offline=settings.llm_provider == "offline")
    yield
    await client.close()


app = FastAPI(title="Gerador de Notas Devolutivas", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(vicios.router)
app.include_router(precedents.router)
app.include_router(devolution.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
