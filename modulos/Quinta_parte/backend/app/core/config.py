from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = Field("", validation_alias=AliasChoices("MONGODB_URI", "MONGO_URI"))
    mongodb_db: str = Field("cartorio_triagem", validation_alias=AliasChoices("MONGODB_DB", "MONGO_DB"))

    # "auto" escolhe gemini > openai > heuristic conforme as chaves disponíveis
    llm_provider: Literal["auto", "gemini", "openai", "heuristic"] = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # Usados em ordem quando o modelo principal responde 429/503 (sobrecarga)
    gemini_fallback_models: Annotated[list[str], NoDecode] = []
    gemini_thinking_level: str = "low"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_timeout_s: float = 60

    # Cartório
    office_name: str = "Cartório de Notas"
    office_state: str = "SP"
    fee_disclaimer: str = (
        "Este valor é uma estimativa preliminar baseada nas informações prestadas. "
        "A conferência definitiva de valores ocorrerá na lavratura do ato."
    )

    # Cria 3 atendimentos fictícios quando o banco está vazio (útil com o repositório em memória)
    demo_data: bool = False

    # Uploads (servidos em /media)
    storage_dir: Path = BACKEND_DIR / "storage"
    max_upload_mb: int = 12

    # Aceita "http://a,http://b" ou JSON '["http://a"]'
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:4220"]

    @field_validator("cors_origins", "gemini_fallback_models", mode="before")
    @classmethod
    def _split_list(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json

                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
