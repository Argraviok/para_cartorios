import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import analyze_continuity, analyze_geometry, parcels
from app.core.config import settings
from app.core.database import init_repository
from app.services.extractor_service import active_engine

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_repository()
    yield


app = FastAPI(title="Confrontação de Matrículas e Memoriais", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(parcels.router)
app.include_router(analyze_continuity.router)
app.include_router(analyze_geometry.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "extraction_engine": active_engine(), "database": "mongodb" if settings.mongodb_uri else "memory"}
