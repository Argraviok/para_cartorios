from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "cartorio_db"

    # Se LLM_PROVIDER não for informado, usa o provedor cuja chave estiver definida.
    llm_provider: Optional[Literal["gemini", "openai"]] = None
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    cors_origins: str = "http://localhost:4230"
    max_pdf_mb: int = 20
    # LibreOffice, usado para converter Word em PDF.
    soffice_path: str = "soffice"

    @property
    def provider(self) -> Optional[str]:
        if self.llm_provider:
            return self.llm_provider
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        return None


settings = Settings()
