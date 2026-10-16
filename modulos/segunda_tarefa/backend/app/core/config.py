import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Provider = Literal["gemini", "openai"]

DEFAULT_EMBEDDING_MODELS: dict[str, str] = {
    "gemini": "gemini-embedding-001",
    "openai": "text-embedding-3-small",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    # Banco
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017/?directConnection=true",
        validation_alias=AliasChoices("MONGO_URI", "MONGODB_URI"),
    )
    mongodb_db: str = Field(default="notas_devolutivas", validation_alias=AliasChoices("MONGO_DB", "MONGODB_DB"))

    # LLM — sem LLM_PROVIDER, usa o provedor cuja chave estiver preenchida.
    # offline = minuta montada só com a redação-modelo das fichas, sem chamar LLM.
    llm_provider: Literal["gemini", "openai", "offline"] | None = None
    gemini_model: str = "gemini-flash-latest"
    openai_model: str = "gpt-4o-mini"
    # Tentados em ordem quando o modelo principal responde 429/500/503 (sobrecarga)
    gemini_fallback_models: Annotated[list[str], NoDecode] = []
    # Sobrescreve GEMINI_MODEL/OPENAI_MODEL quando definido
    llm_model: str | None = None
    # None = não envia o parâmetro (alguns modelos de raciocínio não aceitam temperature)
    llm_temperature: float | None = 0.1
    prompt_version: str = "v1"

    # Embeddings (dimensão fixa: o índice vetorial é criado com este valor).
    # Sem EMBEDDING_PROVIDER, segue o provedor do LLM ou a chave disponível.
    embedding_provider: Provider | None = None
    embedding_model: str | None = None
    embedding_dims: int = 768

    gemini_api_key: str | None = None
    openai_api_key: str | None = None

    # Serventia (cabeçalho, prazo e assinatura da nota)
    serventia_nome: str = "Oficial de Registro de Imóveis da Comarca de Exemplo"
    serventia_cns: str = "00.000-0"
    serventia_endereco: str = "Rua Exemplo, 100 — Centro"
    serventia_cidade_uf: str = "Exemplo/SP"
    oficial_nome: str = "Nome do Oficial"
    # Confirmar com a redação vigente do art. 205 da LRP e as normas da CGJ local
    prenotacao_dias: int = 20

    # Aceita "http://a,http://b" ou JSON '["http://a"]'
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:4240"]

    @field_validator("cors_origins", "gemini_fallback_models", mode="before")
    @classmethod
    def _split_list(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return json.loads(v) if v.startswith("[") else [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("gemini_api_key", "openai_api_key", "llm_model", "embedding_model", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v

    @model_validator(mode="after")
    def _resolve_providers(self):
        available: list[Provider] = [p for p, key in (("gemini", self.gemini_api_key), ("openai", self.openai_api_key)) if key]

        if self.llm_provider is None:
            if len(available) > 1:
                raise ValueError("GEMINI_API_KEY e OPENAI_API_KEY estão preenchidas: defina LLM_PROVIDER=gemini ou openai.")
            self.llm_provider = available[0] if available else None
        if self.llm_model is None and self.llm_provider in ("gemini", "openai"):
            self.llm_model = self.gemini_model if self.llm_provider == "gemini" else self.openai_model

        if self.embedding_provider is None:
            if self.llm_provider in ("gemini", "openai"):
                self.embedding_provider = self.llm_provider
            elif available:
                self.embedding_provider = available[0]
        if self.embedding_model is None and self.embedding_provider:
            self.embedding_model = DEFAULT_EMBEDDING_MODELS[self.embedding_provider]
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
