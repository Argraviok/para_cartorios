import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import ingest, search
from app.core import database
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.init_db()
    yield
    database.close_db()


settings = get_settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Cartório Histórico - OCR & Paleografia", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingest.router)
app.include_router(search.router)
app.mount(settings.media_url_prefix, StaticFiles(directory=settings.storage_dir), name="media")


@app.get("/api/health")
async def health():
    return {"status": "ok", "atlas_search": database.atlas_search_enabled, "vlm_model": settings.vlm_model}
