from datetime import date, datetime, time, timezone
from typing import Protocol

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import COUNTERS, NOTES
from app.schemas.devolution_schema import DevolutionNote


class NoteNotFound(Exception):
    pass


class NoteConflict(Exception):
    pass


class NoteRepository(Protocol):
    async def create(self, fields: dict) -> DevolutionNote: ...
    async def get(self, note_id: str) -> DevolutionNote: ...
    async def update_draft(self, note_id: str, expected_version: int, fields: dict) -> DevolutionNote: ...
    async def claim_for_issue(self, note_id: str) -> DevolutionNote: ...
    async def release_issue_claim(self, note_id: str) -> None: ...
    async def next_number(self, year: int) -> int: ...
    async def finalize_issue(self, note_id: str, fields: dict) -> DevolutionNote: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_bson(fields: dict) -> dict:
    # BSON não tem tipo "date" puro: grava como datetime à meia-noite UTC
    return {
        k: datetime.combine(v, time.min, tzinfo=timezone.utc) if isinstance(v, date) and not isinstance(v, datetime) else v
        for k, v in fields.items()
    }


def _from_bson(doc: dict) -> DevolutionNote:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("protocol_date"), datetime):
        doc["protocol_date"] = doc["protocol_date"].date()
    return DevolutionNote.model_validate(doc)


def _oid(note_id: str) -> ObjectId:
    try:
        return ObjectId(note_id)
    except (InvalidId, TypeError):
        raise NoteNotFound(note_id)


class MongoNoteRepository:
    def __init__(self, db: AsyncDatabase):
        self._notes = db[NOTES]
        self._counters = db[COUNTERS]

    async def create(self, fields: dict) -> DevolutionNote:
        now = _now()
        doc = _to_bson({**fields, "status": "draft", "note_number": None, "version": 1,
                        "created_at": now, "updated_at": now, "issued_at": None})
        result = await self._notes.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _from_bson(doc)

    async def get(self, note_id: str) -> DevolutionNote:
        doc = await self._notes.find_one({"_id": _oid(note_id)})
        if doc is None:
            raise NoteNotFound(note_id)
        return _from_bson(doc)

    async def update_draft(self, note_id: str, expected_version: int, fields: dict) -> DevolutionNote:
        oid = _oid(note_id)
        doc = await self._notes.find_one_and_update(
            {"_id": oid, "status": "draft", "version": expected_version},
            {"$set": {**_to_bson(fields), "updated_at": _now()}, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            await self._raise_why_not_updatable(oid, expected_version)
        return _from_bson(doc)

    async def claim_for_issue(self, note_id: str) -> DevolutionNote:
        """Passa draft → issuing atomicamente; só uma requisição concorrente vence."""
        oid = _oid(note_id)
        doc = await self._notes.find_one_and_update(
            {"_id": oid, "status": "draft"},
            {"$set": {"status": "issuing"}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            await self._raise_why_not_updatable(oid, None)
        return _from_bson(doc)

    async def release_issue_claim(self, note_id: str) -> None:
        await self._notes.update_one({"_id": _oid(note_id), "status": "issuing"}, {"$set": {"status": "draft"}})

    async def next_number(self, year: int) -> int:
        doc = await self._counters.find_one_and_update(
            {"_id": f"devolution_note_{year}"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc["seq"]

    async def finalize_issue(self, note_id: str, fields: dict) -> DevolutionNote:
        now = _now()
        doc = await self._notes.find_one_and_update(
            {"_id": _oid(note_id), "status": "issuing"},
            {"$set": {**fields, "status": "issued", "issued_at": now, "updated_at": now}, "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise NoteConflict("emissão interrompida")
        return _from_bson(doc)

    async def _raise_why_not_updatable(self, oid: ObjectId, expected_version: int | None):
        current = await self._notes.find_one({"_id": oid}, {"status": 1, "version": 1})
        if current is None:
            raise NoteNotFound(str(oid))
        if current["status"] != "draft":
            raise NoteConflict("nota já emitida ou em emissão; não pode ser alterada")
        raise NoteConflict(f"versão desatualizada (atual: {current['version']}, enviada: {expected_version})")
