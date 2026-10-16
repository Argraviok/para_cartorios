from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import ServerSelectionTimeoutError

from app.api.endpoints import qualify, rules
from app.core.config import settings

app = FastAPI(title="Cartório AI - Exame Qualificativo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rules.router)
app.include_router(qualify.router)


@app.exception_handler(ServerSelectionTimeoutError)
async def database_unavailable(request: Request, exc: ServerSelectionTimeoutError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Banco de dados indisponível. Verifique o MongoDB (MONGO_URI)."},
    )
