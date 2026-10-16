import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_token
from app.api.endpoints import fraud_analysis, signature_cards
from app.core import database
from app.core.config import get_settings
from app.services import vlm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    await database.disconnect()


def create_app(use_lifespan: bool = True) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan if use_lifespan else None)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    auth = [Depends(require_token)]
    app.include_router(fraud_analysis.router, dependencies=auth)
    app.include_router(signature_cards.router, dependencies=auth)

    @app.get("/health")
    async def health():
        return {"status": "ok", "vlm_enabled": vlm_client.is_enabled(), "vlm_provider": settings.vlm_provider}

    return app


app = create_app()
