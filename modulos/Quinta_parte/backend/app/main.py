import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import chat, documents, fees
from app.core.config import settings
from app.core.database import init_repository
from app.services.llm_client import engine_label

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_repository()
    if settings.demo_data:
        from app.demo_data import ensure_demo_data

        await ensure_demo_data()
    logging.getLogger(__name__).info("Motor de IA: %s", engine_label())
    yield


app = FastAPI(title="Cartório AI - Triagem e Atendimento Inteligente", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(fees.router)

Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.storage_dir), name="media")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "ai_engine": engine_label(),
        "database": "mongodb" if settings.mongodb_uri else "memory",
        "office": settings.office_name,
    }
