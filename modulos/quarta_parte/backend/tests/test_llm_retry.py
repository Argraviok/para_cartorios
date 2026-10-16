"""Fallback/retry do Gemini com respostas simuladas (não consome cota da API)."""

import asyncio
import json

import httpx
import pytest

from app.core.config import settings
from app.schemas.geo_schema import TitleExtraction
from app.services import extractor_service as ex

QUOTA_429 = {
    "error": {
        "code": 429,
        "message": "You exceeded your current quota",
        "status": "RESOURCE_EXHAUSTED",
        "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "25177s"}],
    }
}
OVERLOAD_503 = {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}


def ok_body(obj):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}


@pytest.fixture
def fake_gemini(monkeypatch):
    """Roteia respostas por modelo; registra as chamadas feitas."""
    calls: list[str] = []
    script: dict[str, list] = {}

    async def fake_post(self, url, json=None, headers=None):
        model = url.split("/models/")[1].split(":")[0]
        calls.append(model)
        item = script[model].pop(0) if len(script[model]) > 1 else script[model][0]
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    async def no_sleep(_):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(ex.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(settings, "gemini_api_key", "test")
    monkeypatch.setattr(settings, "gemini_model", "primary")
    monkeypatch.setattr(settings, "gemini_fallback_models", ["backup"])
    return calls, script


def run(coro):
    return asyncio.run(coro)


def test_daily_quota_skips_retries_and_falls_back(fake_gemini):
    calls, script = fake_gemini
    script["primary"] = [(429, QUOTA_429)]
    script["backup"] = [(200, ok_body({"sellers": ["A"], "buyers": []}))]
    result = run(ex._call_gemini("p", TitleExtraction, "texto", None))
    assert result.sellers == ["A"]
    assert calls == ["primary", "backup"]  # sem repetir o modelo com cota esgotada


def test_transient_503_is_retried_on_same_model(fake_gemini):
    calls, script = fake_gemini
    script["primary"] = [(503, OVERLOAD_503), (200, ok_body({"sellers": [], "buyers": ["B"]}))]
    script["backup"] = [(500, {})]
    assert run(ex._call_gemini("p", TitleExtraction, "t", None)).buyers == ["B"]
    assert calls == ["primary", "primary"]


def test_timeout_falls_back(fake_gemini):
    calls, script = fake_gemini
    script["primary"] = [httpx.ReadTimeout("slow")]
    script["backup"] = [(200, ok_body({"sellers": [], "buyers": []}))]
    run(ex._call_gemini("p", TitleExtraction, "t", None))
    assert calls[-1] == "backup"


def test_all_models_fail_reports_each(fake_gemini):
    _, script = fake_gemini
    script["primary"] = [(429, QUOTA_429)]
    script["backup"] = [(503, OVERLOAD_503)]
    with pytest.raises(ex.ExtractionError) as err:
        run(ex._call_gemini("p", TitleExtraction, "t", None))
    assert "primary" in str(err.value) and "backup" in str(err.value)


def test_schema_violation_becomes_extraction_error(fake_gemini):
    _, script = fake_gemini
    script["primary"] = [(200, ok_body({"sellers": "não é lista"}))]
    with pytest.raises(ex.ExtractionError):
        run(ex._call_gemini("p", TitleExtraction, "t", None))
