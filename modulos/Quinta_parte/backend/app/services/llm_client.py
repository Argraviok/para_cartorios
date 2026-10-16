"""Chamada estruturada (JSON Schema do Pydantic) ao Gemini ou à OpenAI, com suporte a imagem/PDF.

- gemini → generateContent com responseJsonSchema e fallback entre modelos em 429/503.
- openai → Chat Completions com response_format json_schema strict.
- heuristic → nenhum LLM configurado; os serviços usam regras locais.
"""

import asyncio
import base64
import copy
import logging
from typing import Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def active_engine() -> str:
    p = settings.llm_provider
    if p == "auto":
        if settings.gemini_api_key:
            return "gemini"
        if settings.openai_api_key:
            return "openai"
        return "heuristic"
    return p


def engine_label() -> str:
    engine = active_engine()
    if engine == "gemini":
        return f"gemini:{settings.gemini_model}"
    if engine == "openai":
        return f"openai:{settings.openai_model}"
    return "heuristic"


def _schema_for(model_cls: type[BaseModel], exclude: set[str]) -> dict:
    schema = model_cls.model_json_schema()
    for field in exclude:
        schema["properties"].pop(field, None)
        if field in schema.get("required", []):
            schema["required"].remove(field)
    return schema


def _strict_schema(schema: dict) -> dict:
    """Adapta o JSON Schema do Pydantic ao modo strict do OpenAI Structured Outputs."""
    schema = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS = (2, 5)
MAX_RETRY_WAIT_S = 20


def _retry_after_seconds(r: httpx.Response) -> Optional[float]:
    if r.headers.get("retry-after", "").isdigit():
        return float(r.headers["retry-after"])
    try:
        for detail in r.json()["error"].get("details", []):
            if detail.get("@type", "").endswith("RetryInfo"):
                return float(detail["retryDelay"].rstrip("s"))
    except (ValueError, KeyError, AttributeError, TypeError):
        pass
    return None


async def _post_with_retry(url: str, body: dict, headers: dict,
                           delays: tuple[int, ...] = RETRY_DELAYS) -> httpx.Response:
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as client:
        for delay in (*delays, None):
            try:
                r = await client.post(url, json=body, headers=headers)
            except httpx.TransportError as exc:
                if delay is None:
                    raise LLMError(f"Falha de rede/timeout ao chamar o LLM: {exc!r}") from exc
                log.warning("Erro de rede no LLM (%r); nova tentativa em %ss", exc, delay)
            else:
                if r.status_code not in RETRY_STATUS or delay is None:
                    return r
                wait = _retry_after_seconds(r)
                if wait is not None and wait > MAX_RETRY_WAIT_S:
                    return r
                delay = max(delay, wait or 0)
                log.warning("LLM retornou %s; nova tentativa em %ss", r.status_code, delay)
            await asyncio.sleep(delay)
    raise AssertionError("inalcançável")


def _error_message(r: httpx.Response) -> str:
    try:
        return r.json()["error"]["message"].split("\n")[0][:200]
    except (ValueError, KeyError, TypeError):
        return r.text[:200]


async def _call_gemini(system: str, user_text: str, media: Optional[tuple[bytes, str]],
                       schema: dict) -> tuple[str, str]:
    parts: list[dict] = [{"text": user_text}]
    if media:
        data, mime = media
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
    generation_config: dict = {
        "temperature": 0.2,
        "responseMimeType": "application/json",
        "responseJsonSchema": schema,
    }
    if settings.gemini_thinking_level:
        generation_config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
    }
    models = [settings.gemini_model, *settings.gemini_fallback_models]
    failures: list[str] = []
    for i, model in enumerate(models):
        is_last = i == len(models) - 1
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = await _post_with_retry(url, body, {"x-goog-api-key": settings.gemini_api_key},
                                       RETRY_DELAYS if is_last else (2,))
        except LLMError as exc:
            failures.append(f"{model}: {exc}")
            if is_last:
                raise LLMError("Nenhum modelo Gemini respondeu. " + " | ".join(failures)) from exc
            continue
        if r.status_code == 200:
            try:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"], f"gemini:{model}"
            except (KeyError, IndexError, ValueError) as exc:
                raise LLMError(f"Resposta inesperada do Gemini ({model}): {r.text[:300]}") from exc
        failures.append(f"{model}: HTTP {r.status_code} {_error_message(r)}")
        if r.status_code in RETRY_STATUS and not is_last:
            log.warning("Gemini %s indisponível (%s); usando %s", model, r.status_code, models[i + 1])
            continue
        break
    raise LLMError("Gemini falhou. " + " | ".join(failures))


async def _call_openai(system: str, user_text: str, media: Optional[tuple[bytes, str]],
                       schema: dict, name: str) -> str:
    content: list[dict] = [{"type": "text", "text": user_text}]
    if media:
        data, mime = media
        b64 = base64.b64encode(data).decode()
        if mime == "application/pdf":
            content.append({"type": "file", "file": {"filename": "documento.pdf",
                                                      "file_data": f"data:{mime};base64,{b64}"}})
        else:
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    body = {
        "model": settings.openai_model,
        "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": name, "strict": True, "schema": _strict_schema(schema)}},
    }
    r = await _post_with_retry("https://api.openai.com/v1/chat/completions", body,
                               {"Authorization": f"Bearer {settings.openai_api_key}"})
    if r.status_code != 200:
        raise LLMError(f"OpenAI retornou {r.status_code}: {_error_message(r)}")
    msg = r.json()["choices"][0]["message"]
    if msg.get("refusal"):
        raise LLMError(f"OpenAI recusou: {msg['refusal']}")
    return msg["content"]


async def call_structured(system: str, user_text: str, model_cls: type[T],
                          media: Optional[tuple[bytes, str]] = None,
                          exclude_fields: frozenset[str] = frozenset()) -> tuple[T, str]:
    """Chama o LLM ativo e valida a resposta no schema. Devolve (resultado, "provedor:modelo").

    Levanta LLMError em qualquer falha."""
    engine = active_engine()
    schema = _schema_for(model_cls, set(exclude_fields))
    if engine == "gemini":
        raw, used = await _call_gemini(system, user_text, media, schema)
    elif engine == "openai":
        raw = await _call_openai(system, user_text, media, schema, model_cls.__name__)
        used = f"openai:{settings.openai_model}"
    else:
        raise LLMError("Nenhum LLM configurado (GEMINI_API_KEY / OPENAI_API_KEY).")
    try:
        return model_cls.model_validate_json(raw), used
    except ValidationError as exc:
        raise LLMError(f"LLM devolveu JSON fora do schema {model_cls.__name__}: {exc}") from exc
