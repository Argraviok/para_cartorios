from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Cartório AI - Anonimização LGPD"

    # MongoDB Atlas. Vazio => repositório em memória (somente desenvolvimento/testes).
    mongodb_uri: str = ""
    mongodb_db: str = "cartorio_lgpd"

    # Armazenamento dos binários. O original é gravado uma única vez e nunca sobrescrito.
    storage_dir: Path = Path("./storage")
    max_upload_mb: int = 50

    # Conversão de .docx/.doc para PDF (LibreOffice headless).
    soffice_path: str = "soffice"
    conversion_timeout_seconds: float = 120.0

    # Motor LLM para detecção contextual. "none" => apenas regras determinísticas.
    # ATENÇÃO: habilitar envia o texto do documento a um provedor externo (LGPD art. 33).
    llm_provider: Literal["none", "gemini", "openai"] = "none"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_chunk_chars: int = 12000

    # Após a sanitização, substitui `detected_text` no MongoDB por um marcador,
    # para que o banco não retenha os dados que foram tarjados.
    purge_detected_text_on_finalize: bool = True

    cors_origins: list[str] = ["http://localhost:4200"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
