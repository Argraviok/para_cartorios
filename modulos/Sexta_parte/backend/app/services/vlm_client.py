"""Cliente VLM multimodal com saída estruturada (Gemini ou OpenAI) via REST.

O schema JSON é imposto pelo provedor e a resposta é revalidada com Pydantic; qualquer falha
vira VLMError e o laudo segue apenas com as heurísticas locais.
"""
import base64
import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)


class VLMError(Exception):
    pass


class VLMImage(BaseModel):
    data: bytes
    mime_type: str = "image/jpeg"
    label: str = ""


def is_enabled() -> bool:
    s = get_settings()
    return (s.vlm_provider == "gemini" and bool(s.gemini_api_key)) or (
        s.vlm_provider == "openai" and bool(s.openai_api_key)
    )


async def analyze(prompt: str, images: list[VLMImage], json_schema: dict, model: type[T]) -> T:
    """`json_schema` deve ser compatível com o modo strict da OpenAI (todas as chaves required,
    additionalProperties=false) — esse subconjunto também é aceito pelo Gemini."""
    s = get_settings()
    if not is_enabled():
        raise VLMError("VLM desabilitado")
    try:
        if s.vlm_provider == "gemini":
            raw = await _call_gemini(prompt, images, json_schema)
        else:
            raw = await _call_openai(prompt, images, json_schema)
        return model.model_validate(json.loads(raw))
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as exc:
        raise VLMError(f"{type(exc).__name__}: {str(exc)[:300]}") from exc


def _gemini_schema(schema: dict) -> dict:
    """Remove chaves não suportadas pelo responseSchema do Gemini."""
    if isinstance(schema, dict):
        return {k: _gemini_schema(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_gemini_schema(v) for v in schema]
    return schema


async def _call_gemini(prompt: str, images: list[VLMImage], json_schema: dict) -> str:
    s = get_settings()
    parts: list[dict] = [{"text": prompt}]
    for img in images:
        if img.label:
            parts.append({"text": img.label})
        parts.append({"inline_data": {"mime_type": img.mime_type, "data": base64.b64encode(img.data).decode()}})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": _gemini_schema(json_schema),
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent"
    async with httpx.AsyncClient(timeout=s.vlm_timeout_seconds) as client:
        resp = await client.post(url, json=body, headers={"x-goog-api-key": s.gemini_api_key})
        resp.raise_for_status()
        data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_openai(prompt: str, images: list[VLMImage], json_schema: dict) -> str:
    s = get_settings()
    content: list[dict] = [{"type": "text", "text": prompt}]
    for img in images:
        if img.label:
            content.append({"type": "text", "text": img.label})
        b64 = base64.b64encode(img.data).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{img.mime_type};base64,{b64}", "detail": "high"}})
    body = {
        "model": s.openai_model,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": content}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "laudo", "strict": True, "schema": json_schema},
        },
    }
    async with httpx.AsyncClient(timeout=s.vlm_timeout_seconds) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {s.openai_api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]
