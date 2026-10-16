import logging
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger(__name__)

TRANSIENT_STATUS = {429, 500, 503}


class LLMClient(Protocol):
    model: str

    async def generate_structured(self, system: str, user: str, schema: type[T]) -> tuple[T, str]:
        """Retorna a saída validada e o nome do modelo que efetivamente respondeu."""
        ...


class GeminiClient:
    def __init__(self, api_key: str, model: str, temperature: float | None, fallback_models: list[str] | None = None):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._models = [model, *(m for m in fallback_models or [] if m != model)]
        self._temperature = temperature

    async def generate_structured(self, system: str, user: str, schema: type[T]) -> tuple[T, str]:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=self._temperature,
        )
        last_exc: Exception | None = None
        for model in self._models:
            try:
                resp = await self._client.aio.models.generate_content(model=model, contents=user, config=config)
            except errors.APIError as exc:
                if exc.code not in TRANSIENT_STATUS:
                    raise
                log.warning("Gemini %s indisponível (%s); tentando o próximo modelo", model, exc.code)
                last_exc = exc
                continue
            return schema.model_validate_json(resp.text), model
        raise last_exc


class OpenAIClient:
    def __init__(self, api_key: str, model: str, temperature: float | None):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._temperature = temperature

    async def generate_structured(self, system: str, user: str, schema: type[T]) -> tuple[T, str]:
        kwargs = {"temperature": self._temperature} if self._temperature is not None else {}
        resp = await self._client.responses.parse(
            model=self.model, instructions=system, input=user, text_format=schema, **kwargs
        )
        if resp.output_parsed is None:
            raise ValueError("LLM não retornou saída estruturada")
        return resp.output_parsed, self.model


def build_llm(settings: Settings) -> LLMClient | None:
    if settings.llm_provider == "offline":
        return None
    if settings.llm_provider is None:
        raise RuntimeError("nenhuma chave de LLM configurada (GEMINI_API_KEY ou OPENAI_API_KEY)")
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")
        return GeminiClient(settings.gemini_api_key, settings.llm_model, settings.llm_temperature, settings.gemini_fallback_models)
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    return OpenAIClient(settings.openai_api_key, settings.llm_model, settings.llm_temperature)
