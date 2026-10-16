"""Geocodificação com Nominatim simulado (sem rede)."""

import asyncio

import httpx
import pytest

from app.core.config import settings
from app.schemas.geo_schema import PropertyAddress
from app.services import geocoding_service as geo


@pytest.fixture
def nominatim(monkeypatch):
    queries: list[dict] = []
    answers: dict[str, list] = {}

    async def fake_get(self, url, params=None, headers=None):
        queries.append(params)
        assert "User-Agent" in headers
        key = params.get("street") or params.get("q") or "city"
        if key == "fail":
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json=answers.get(key, []), request=httpx.Request("GET", url))

    async def no_sleep(_):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(geo.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(settings, "geocoding_enabled", True)
    geo._cache.clear()
    return queries, answers


ADDR = PropertyAddress(street="Rua das Acácias", number="120", subdivision="Jardim das Acácias", city="Campinas", state="SP")


def test_most_precise_match_wins(nominatim):
    queries, answers = nominatim
    answers["120 Rua das Acácias"] = [{"lat": "-22.9", "lon": "-47.06", "display_name": "Rua das Acácias, 120"}]
    loc = asyncio.run(geo.geocode_address(ADDR))
    assert loc.precision == "ENDERECO" and loc.lat == -22.9
    assert len(queries) == 1 and queries[0]["countrycodes"] == "br"


def test_falls_back_to_subdivision_then_city(nominatim):
    queries, answers = nominatim
    answers["Jardim das Acácias, Campinas, SP, Brasil"] = [{"lat": "-22.91", "lon": "-47.07"}]
    loc = asyncio.run(geo.geocode_address(ADDR))
    assert loc.precision == "BAIRRO"
    assert [q.get("street") or q.get("q") for q in queries][:2] == ["120 Rua das Acácias", "Rua das Acácias"]

    geo._cache.clear()
    answers.clear()
    answers["city"] = [{"lat": "-22.95", "lon": "-47.1"}]
    assert asyncio.run(geo.geocode_address(ADDR)).precision == "CIDADE"


def test_network_failure_returns_none(nominatim):
    assert asyncio.run(geo.geocode_address(PropertyAddress(street="fail", city="Campinas"))) is None


def test_without_city_or_disabled(nominatim, monkeypatch):
    assert asyncio.run(geo.geocode_address(PropertyAddress(street="Rua X"))) is None
    monkeypatch.setattr(settings, "geocoding_enabled", False)
    assert asyncio.run(geo.geocode_address(ADDR)) is None


def test_results_are_cached(nominatim):
    queries, answers = nominatim
    answers["120 Rua das Acácias"] = [{"lat": "-22.9", "lon": "-47.06"}]
    asyncio.run(geo.geocode_address(ADDR))
    asyncio.run(geo.geocode_address(ADDR))
    assert len(queries) == 1
