from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Cartório AI - Prevenção à Fraude e Due Diligence"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "cartorio_antifraude"

    # Armazenamento criptografado (LGPD). Gere com:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    storage_dir: Path = Path("./storage")
    storage_encryption_key: str = ""

    # Retenção (dias) dos arquivos de documentos/biometria após a decisão do oficial.
    retention_days: int = 180

    # Motor VLM: "none" usa apenas heurísticas locais (OpenCV/ELA).
    vlm_provider: Literal["none", "gemini", "openai"] = "none"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    vlm_timeout_seconds: float = 60.0

    # Procurações lavradas há mais tempo que isso exigem reconfirmação na CENSEC.
    procuration_alert_days: int = 5 * 365
    # Certidão de não-revogação considerada recente até X dias.
    censec_confirmation_max_age_days: int = 30

    # Token Bearer exigido em todas as rotas /api quando definido (recomendado em produção).
    api_token: str = ""

    max_upload_mb: int = 15
    cors_origins: list[str] = ["http://localhost:4260"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
