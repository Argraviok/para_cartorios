"""Classificação contextual via LLM (Gemini ou OpenAI) com saída estruturada.

O LLM recebe o texto das páginas e devolve os trechos *literais* a ocultar; a
localização em coordenadas é feita depois, pelo índice de layout, para que o
modelo nunca invente posições.
"""

import json
from dataclasses import dataclass

import httpx

from app.core.config import Settings

CATEGORIES = ["DADO_MEDICO", "DADO_BANCARIO", "FILIACAO_PROTEGIDA", "DADO_FINANCEIRO"]

SYSTEM_PROMPT = """Você é um assistente de conformidade LGPD de uma serventia extrajudicial brasileira.
Receberá o texto de páginas de certidões e autos (registro civil, imóveis, notas).
Identifique trechos com dados pessoais SENSÍVEIS DE TERCEIROS que devem ser tarjados antes da expedição:
- DADO_MEDICO: diagnósticos, doenças, CIDs, laudos médicos/psiquiátricos, internações, deficiências (ex.: em processos de curatela/interdição).
- DADO_BANCARIO: bancos, agências, contas, chaves PIX, cartões.
- DADO_FINANCEIRO: saldos, rendimentos, salários, dívidas, patrimônio de terceiros.
- FILIACAO_PROTEGIDA: menções à origem de filiação sob sigilo (adoção, pais biológicos, destituição do poder familiar, investigação de paternidade).
Regras:
- Copie o trecho EXATAMENTE como aparece no texto (mesmas palavras e grafia), sem parafrasear.
- Seja mínimo: inclua apenas as palavras que revelam o dado sensível.
- NÃO marque nomes das partes, datas, números de matrícula/livro/folha nem valores de negócios jurídicos (preço de imóvel em escritura), que integram o teor do ato.
- Se não houver nada, devolva uma lista vazia."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page_number": {"type": "integer"},
                    "text": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "pii_type": {"type": "string"},
                },
                "required": ["page_number", "text", "category", "pii_type"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class LlmFinding:
    page_number: int
    text: str
    category: str
    pii_type: str


class LlmError(Exception):
    pass


def _chunk_pages(pages: dict[int, str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for number, text in pages.items():
        block = f"\n=== PÁGINA {number} ===\n{text}\n"
        if current and len(current) + len(block) > max_chars:
            chunks.append(current)
            current = ""
        current += block
    if current:
        chunks.append(current)
    return chunks


async def _call_gemini(client: httpx.AsyncClient, settings: Settings, user_text: str) -> dict:
    schema = json.loads(json.dumps(RESPONSE_SCHEMA))
    schema["properties"]["findings"]["items"].pop("additionalProperties")
    schema.pop("additionalProperties")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    resp = await client.post(
        url,
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        },
    )
    resp.raise_for_status()
    return json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])


async def _call_openai(client: httpx.AsyncClient, settings: Settings, user_text: str) -> dict:
    resp = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.openai_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "pii_findings", "strict": True, "schema": RESPONSE_SCHEMA},
            },
        },
    )
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


async def classify_pages(settings: Settings, pages: dict[int, str]) -> list[LlmFinding]:
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise LlmError("GEMINI_API_KEY não configurada")
        call = _call_gemini
    elif settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise LlmError("OPENAI_API_KEY não configurada")
        call = _call_openai
    else:
        return []

    findings: list[LlmFinding] = []
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        for chunk in _chunk_pages(pages, settings.llm_chunk_chars):
            try:
                data = await call(client, settings, chunk)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
                raise LlmError(f"Falha na chamada ao LLM ({settings.llm_provider}): {type(exc).__name__}") from exc
            for f in data.get("findings", []):
                if f.get("category") in CATEGORIES and f.get("text", "").strip():
                    findings.append(LlmFinding(int(f["page_number"]), f["text"], f["category"], f["pii_type"]))
    return findings
