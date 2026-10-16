import math
from typing import Literal, Protocol

from app.core.config import Settings

EmbeddingTask = Literal["query", "document"]


class Embedder(Protocol):
    model: str

    async def embed(self, text: str, task: EmbeddingTask) -> list[float]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


class GeminiEmbedder:
    def __init__(self, api_key: str, model: str, dims: int):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._dims = dims

    async def embed(self, text: str, task: EmbeddingTask) -> list[float]:
        from google.genai import types

        resp = await self._client.aio.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=self._dims,
                task_type="RETRIEVAL_QUERY" if task == "query" else "RETRIEVAL_DOCUMENT",
            ),
        )
        # Saídas com dimensão reduzida não vêm normalizadas
        return _l2_normalize(list(resp.embeddings[0].values))


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, dims: int):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._dims = dims

    async def embed(self, text: str, task: EmbeddingTask) -> list[float]:
        resp = await self._client.embeddings.create(model=self.model, input=text, dimensions=self._dims)
        return resp.data[0].embedding


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider is None:
        raise RuntimeError("nenhuma chave de embeddings configurada (GEMINI_API_KEY ou OPENAI_API_KEY)")
    if settings.embedding_provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")
        return GeminiEmbedder(settings.gemini_api_key, settings.embedding_model, settings.embedding_dims)
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    return OpenAIEmbedder(settings.openai_api_key, settings.embedding_model, settings.embedding_dims)
