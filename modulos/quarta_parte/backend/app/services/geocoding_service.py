"""Localização aproximada do imóvel a partir do endereço da matrícula (OpenStreetMap Nominatim).

Política de uso do Nominatim público: no máximo 1 requisição/s, User-Agent identificando a aplicação
e cache dos resultados. Para volume maior, aponte NOMINATIM_URL para uma instância própria.
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas.geo_schema import ApproximateLocation, PropertyAddress

log = logging.getLogger(__name__)

_cache: dict[tuple, Optional[dict]] = {}
_lock = asyncio.Lock()
_last_request = 0.0


def _clean(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip(" ,.;")
    return value or None


def _attempts(addr: PropertyAddress) -> list[tuple[str, dict]]:
    """Consultas da mais precisa para a menos precisa."""
    city, state = _clean(addr.city), _clean(addr.state)
    if not city:
        return []
    base = {"city": city, "country": "Brasil"}
    if state:
        base["state"] = state
    street, number = _clean(addr.street), _clean(addr.number)
    attempts: list[tuple[str, dict]] = []
    if street and number:
        attempts.append(("ENDERECO", {**base, "street": f"{number} {street}"}))
    if street:
        attempts.append(("RUA", {**base, "street": street}))
    for area in (_clean(addr.neighborhood), _clean(addr.subdivision)):
        if area:
            # Bairro/loteamento não tem campo estruturado próprio: busca livre
            attempts.append(("BAIRRO", {"q": ", ".join(filter(None, [area, city, state, "Brasil"]))}))
    attempts.append(("CIDADE", base))
    return attempts


async def _search(params: dict) -> Optional[dict]:
    global _last_request
    key = tuple(sorted(params.items()))
    if key in _cache:
        return _cache[key]
    async with _lock:
        wait = 1.0 - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{settings.nominatim_url.rstrip('/')}/search",
                    params={**params, "format": "jsonv2", "limit": 1, "countrycodes": "br"},
                    headers={"User-Agent": settings.nominatim_user_agent, "Accept-Language": "pt-BR"},
                )
        finally:
            _last_request = time.monotonic()
    r.raise_for_status()
    results = r.json()
    hit = results[0] if results else None
    _cache[key] = hit
    return hit


async def geocode_address(addr: Optional[PropertyAddress]) -> Optional[ApproximateLocation]:
    """Melhor localização encontrada, ou None (desabilitado, sem cidade ou serviço indisponível)."""
    if not settings.geocoding_enabled or addr is None:
        return None
    for precision, params in _attempts(addr):
        try:
            hit = await _search(params)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Geocodificação indisponível (%s); seguindo sem localização aproximada", exc)
            return None
        if hit:
            query = params.get("q") or ", ".join(
                filter(None, [params.get("street"), params.get("city"), params.get("state")])
            )
            return ApproximateLocation(
                lat=float(hit["lat"]),
                lon=float(hit["lon"]),
                precision=precision,
                query=query,
                display_name=hit.get("display_name"),
            )
    return None
