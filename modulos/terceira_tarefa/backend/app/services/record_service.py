"""Montagem de documentos e busca em `historical_records`."""
import html
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import OperationFailure

from app.core import database
from app.core.config import get_settings
from app.schemas.transcription_schema import HistoricalTranscriptionResult
from app.services.phonetic_service import phonetic_name, phonetic_tokens

logger = logging.getLogger(__name__)

SEARCH_PROJECTION_EXCLUDE = {"search_phonetic": 0}


def new_record_id(book_type: str, book_number: str, page_number: int) -> str:
    book = re.sub(r"[^0-9A-Za-z]+", "", book_number).lower() or "x"
    return f"rec_{book_type}_{book}_fl{page_number}_{uuid.uuid4().hex[:8]}"


def enrich_parties(parties: list[dict]) -> list[dict]:
    return [{**p, "phonetic": phonetic_name(p["name_standardized"])} for p in parties]


def build_search_phonetic(parties: list[dict], relatives: list[str]) -> list[str]:
    """Códigos fonéticos de nomes standardized + original + confrontantes/filiação, sem duplicatas."""
    tokens: set[str] = set()
    for p in parties:
        tokens.update(phonetic_tokens(p["name_standardized"]))
        tokens.update(phonetic_tokens(p["name_original"]))
    for r in relatives:
        tokens.update(phonetic_tokens(r))
    return sorted(tokens)


def build_record(
    *,
    record_id: str,
    book_type: str,
    book_number: str,
    page_number: int,
    image_url: str,
    image_enhanced_url: str | None,
    result: HistoricalTranscriptionResult,
    vlm_model: str | None,
) -> dict[str, Any]:
    parties = enrich_parties([p.model_dump() for p in result.parties])
    relatives = result.confrontants_or_parents
    return {
        "_id": record_id,
        "book_type": book_type,
        "book_number": book_number,
        "page_number": page_number,
        "entry_number": result.entry_number,
        "entry_date_text": result.entry_date_text,
        "entry_date_iso": result.entry_date_iso,
        "image_url": image_url,
        "image_enhanced_url": image_enhanced_url,
        "transcription_raw": result.transcription_raw,
        "status": "analyzed",
        "parties": parties,
        "confrontants_or_relatives": relatives,
        "search_phonetic": build_search_phonetic(parties, relatives),
        "confidence_score": result.confidence_score,
        "vlm_model": vlm_model,
        "created_at": datetime.now(timezone.utc),
    }


def _filters(book_type: str | None, status: str | None, year_from: int | None, year_to: int | None) -> dict:
    match: dict[str, Any] = {}
    if book_type:
        match["book_type"] = book_type
    if status:
        match["status"] = status
    date_range: dict[str, str] = {}
    if year_from:
        date_range["$gte"] = f"{year_from:04d}-01-01"
    if year_to:
        date_range["$lte"] = f"{year_to:04d}-12-31"
    if date_range:
        match["entry_date_iso"] = date_range
    return match


async def search_records(
    q: str,
    *,
    book_type: str | None = None,
    status: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 20,
    skip: int = 0,
) -> tuple[str, int, list[dict]]:
    coll = database.get_collection()
    match = _filters(book_type, status, year_from, year_to)
    q = q.strip()

    if not q:
        total = await coll.count_documents(match)
        cursor = coll.find(match, SEARCH_PROJECTION_EXCLUDE).sort("created_at", -1).skip(skip).limit(limit)
        return "fallback", total, await cursor.to_list(length=limit)

    if database.atlas_search_enabled:
        try:
            return ("atlas_search", *await _atlas_search(q, match, limit, skip))
        except OperationFailure as exc:
            # Ex.: índice ainda em construção logo após o primeiro deploy.
            logger.warning("Atlas Search falhou, usando fallback: %s", exc.details)
    return ("fallback", *await _fallback_search(q, match, limit, skip))


async def _atlas_search(q: str, match: dict, limit: int, skip: int) -> tuple[int, list[dict]]:
    name_paths = ["parties.name_standardized", "parties.name_original"]
    phonetic = phonetic_tokens(q)
    should: list[dict] = [
        # Frase exata do nome tem o maior peso.
        {"phrase": {"query": q, "path": name_paths, "slop": 1, "score": {"boost": {"value": 6}}}},
        # Fuzzy (Levenshtein) cobre erros de digitação e de leitura do VLM.
        {"text": {"query": q, "path": name_paths, "fuzzy": {"maxEdits": 2, "prefixLength": 1},
                  "score": {"boost": {"value": 3}}}},
        {"text": {"query": q, "path": "confrontants_or_relatives", "fuzzy": {"maxEdits": 1, "prefixLength": 1},
                  "score": {"boost": {"value": 1.5}}}},
        {"text": {"query": q, "path": "transcription_raw", "fuzzy": {"maxEdits": 1, "prefixLength": 2}}},
        {"text": {"query": q, "path": ["entry_number", "book_number"], "score": {"boost": {"value": 8}}}},
    ]
    if phonetic:
        # Fonética cobre variações históricas que o fuzzy não alcança (Thereza/Teresa, Ignacio/Inácio).
        should.append({"text": {"query": " ".join(phonetic), "path": "search_phonetic",
                                "score": {"boost": {"value": 2.5}}}})

    pipeline: list[dict] = [
        {"$search": {
            "index": get_settings().atlas_search_index,
            "compound": {"should": should, "minimumShouldMatch": 1},
            "highlight": {"path": name_paths + ["transcription_raw", "confrontants_or_relatives"]},
        }},
        {"$match": match} if match else None,
        {"$project": {**SEARCH_PROJECTION_EXCLUDE,
                      "score": {"$meta": "searchScore"},
                      "highlights_raw": {"$meta": "searchHighlights"}}},
        {"$facet": {"total": [{"$count": "n"}], "items": [{"$skip": skip}, {"$limit": limit}]}},
    ]
    pipeline = [stage for stage in pipeline if stage]
    facet = await database.get_collection().aggregate(pipeline).to_list(length=1)
    data = facet[0] if facet else {"total": [], "items": []}
    total = data["total"][0]["n"] if data["total"] else 0
    items = data["items"]
    for item in items:
        item["highlights"] = _format_highlights(item.pop("highlights_raw", []))
    return total, items


def _format_highlights(raw: list[dict]) -> list[str]:
    """Converte searchHighlights do Atlas em trechos com <mark>."""
    snippets = []
    for h in raw[:4]:
        parts = []
        for t in h.get("texts", []):
            value = html.escape(t["value"])
            parts.append(f"<mark>{value}</mark>" if t["type"] == "hit" else value)
        snippets.append("".join(parts).strip())
    return [s for s in snippets if s]


async def _fallback_search(q: str, match: dict, limit: int, skip: int) -> tuple[int, list[dict]]:
    """Busca sem Atlas Search: fonética por token + regex em número de registro e transcrição."""
    phonetic = phonetic_tokens(q)
    escaped = re.escape(q)
    alternatives: list[dict] = [
        {"entry_number": {"$regex": escaped, "$options": "i"}},
        {"transcription_raw": {"$regex": escaped, "$options": "i"}},
        {"parties.name_standardized": {"$regex": escaped, "$options": "i"}},
    ]
    if phonetic:
        alternatives.insert(0, {"search_phonetic": {"$all": phonetic}})
    query = {**match, "$or": alternatives}

    coll = database.get_collection()
    total = await coll.count_documents(query)
    pipeline = [
        {"$match": query},
        {"$addFields": {"score": {"$size": {"$setIntersection": ["$search_phonetic", phonetic]}}}},
        {"$sort": {"score": -1, "created_at": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$project": SEARCH_PROJECTION_EXCLUDE},
    ]
    items = await coll.aggregate(pipeline).to_list(length=limit)
    for item in items:
        item["highlights"] = _fallback_highlights(item, q)
    return total, items


def _fallback_highlights(item: dict, q: str) -> list[str]:
    q_codes = set(phonetic_tokens(q))
    out = []
    for p in item.get("parties", []):
        words = p["name_standardized"].split()
        if any(phonetic_tokens(w) and phonetic_tokens(w)[0] in q_codes for w in words):
            out.append(" ".join(
                f"<mark>{html.escape(w)}</mark>" if phonetic_tokens(w) and phonetic_tokens(w)[0] in q_codes else html.escape(w)
                for w in words
            ))
    return out[:4]
