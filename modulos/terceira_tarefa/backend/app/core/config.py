from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27019/?directConnection=true"
    mongo_db: str = "cartorio_historico"
    mongo_collection: str = "historical_records"
    atlas_search_index: str = "historical_records_search"

    # VLM (Claude). Sem ANTHROPIC_API_KEY o SDK usa as demais fontes de credencial do ambiente.
    anthropic_api_key: str | None = None
    vlm_model: str = "claude-haiku-5-5"
    vlm_effort: str = "high"
    vlm_max_tokens: int = 16000

    # Imagem enviada ao VLM: lado maior em pixels após o pré-processamento.
    vlm_image_max_side: int = 2400

    storage_dir: Path = BASE_DIR / "storage"
    media_url_prefix: str = "/media"
    cors_origins: list[str] = ["http://localhost:4250"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
