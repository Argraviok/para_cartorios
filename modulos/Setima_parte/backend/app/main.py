from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import redact_analysis, redact_apply
from app.core import database
from app.core.config import get_settings
from app.core.legal_basis import CATEGORY_POLICIES


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.connect()
    yield
    await database.disconnect()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(redact_analysis.router)
app.include_router(redact_apply.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "llm_provider": settings.llm_provider, "database": "mongodb" if settings.mongodb_uri else "memory"}


@app.get("/api/redact/categories")
async def categories():
    return {k: {"label": p.label, "legal_basis": p.legal_basis, "approved_by_default": p.approved_by_default} for k, p in CATEGORY_POLICIES.items()}
