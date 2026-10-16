from types import SimpleNamespace

import pytest
from google.genai import errors
from pydantic import BaseModel

from app.services.llm_service import GeminiClient


class Out(BaseModel):
    resposta: str


def client_with(responses: dict[str, object]) -> tuple[GeminiClient, list[str]]:
    calls: list[str] = []

    async def generate_content(model, contents, config):
        calls.append(model)
        r = responses[model]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(text=r)

    c = GeminiClient("chave-falsa", "principal", 0.1, ["reserva-1", "reserva-2"])
    c._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    return c, calls


def api_error(code: int) -> errors.APIError:
    return errors.ServerError(code, {"error": {"code": code, "message": "x", "status": "UNAVAILABLE"}}) if code >= 500 \
        else errors.ClientError(code, {"error": {"code": code, "message": "x", "status": "X"}})


async def test_falls_back_on_overload_and_reports_model_used():
    c, calls = client_with({"principal": api_error(503), "reserva-1": api_error(429), "reserva-2": '{"resposta": "ok"}'})
    out, model = await c.generate_structured("s", "u", Out)
    assert out.resposta == "ok" and model == "reserva-2"
    assert calls == ["principal", "reserva-1", "reserva-2"]


async def test_non_transient_error_is_not_masked():
    c, calls = client_with({"principal": api_error(400), "reserva-1": '{"resposta": "ok"}'})
    with pytest.raises(errors.ClientError):
        await c.generate_structured("s", "u", Out)
    assert calls == ["principal"]


async def test_all_overloaded_raises_last_error():
    c, _ = client_with({m: api_error(503) for m in ("principal", "reserva-1", "reserva-2")})
    with pytest.raises(errors.ServerError):
        await c.generate_structured("s", "u", Out)
