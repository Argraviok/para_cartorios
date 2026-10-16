from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = Field("", validation_alias=AliasChoices("MONGODB_URI", "MONGO_URI"))
    mongodb_db: str = Field("land_registry", validation_alias=AliasChoices("MONGODB_DB", "MONGO_DB"))
    mongodb_collection: str = "land_registry_analyses"

    # "auto" escolhe gemini > openai > heuristic conforme as chaves disponíveis
    llm_provider: Literal["auto", "gemini", "openai", "heuristic"] = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # Usados em ordem quando o modelo principal responde 429/503 (sobrecarga)
    gemini_fallback_models: Annotated[list[str], NoDecode] = []
    # Gemini 3.x: "low" reduz latência; extração estruturada não precisa de raciocínio longo
    gemini_thinking_level: str = "low"
    llm_timeout_s: float = 180
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Regras de qualidade registral
    area_tolerance_percent: float = 5.0
    closure_tolerance_m: float = 0.02  # "fechamento perfeito" (< 2 cm)
    closure_max_acceptable_m: float = 0.50  # acima disso o perímetro "não fecha"
    default_utm_zone: int = 23  # fuso de Campinas/SP e boa parte do Sudeste

    # Localização aproximada pelo endereço (OpenStreetMap Nominatim)
    geocoding_enabled: bool = True
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "confrontacao-matriculas-mvp/0.1"

    # Aceita "http://a,http://b" ou JSON '["http://a"]'
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:4210"]

    @field_validator("cors_origins", "gemini_fallback_models", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json

                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


settings = Settings()
