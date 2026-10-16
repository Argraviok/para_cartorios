from datetime import datetime, timezone
from typing import Protocol

from pymongo.asynchronous.database import AsyncDatabase

from app.core.database import PRECEDENTS
from app.schemas.precedent_schema import PrecedentBase, PrecedentOut


class PrecedentRepository(Protocol):
    async def list_all(self) -> list[PrecedentOut]: ...
    async def upsert(self, precedent_id: str, data: PrecedentBase, embedding: list[float] | None, embedding_model: str | None) -> PrecedentOut: ...


def to_document(precedent_id: str, data: PrecedentBase, embedding: list[float] | None, embedding_model: str | None) -> dict:
    return {
        "_id": precedent_id,
        **data.model_dump(mode="json"),
        "embedding_text": data.build_embedding_text(),
        "embedding": embedding,
        "embedding_model": embedding_model,
        # Toda ficha criada ou alterada volta para revisão jurídica
        "verified": False,
        "verified_by": None,
        "verified_at": None,
        "updated_at": datetime.now(timezone.utc),
    }


def _from_bson(doc: dict) -> PrecedentOut:
    doc = {k: v for k, v in doc.items() if k not in ("embedding", "embedding_text")}
    doc["id"] = doc.pop("_id")
    return PrecedentOut.model_validate(doc)


class MongoPrecedentRepository:
    def __init__(self, db: AsyncDatabase):
        self._coll = db[PRECEDENTS]

    async def list_all(self) -> list[PrecedentOut]:
        cursor = self._coll.find({}, {"embedding": 0}).sort("_id", 1)
        return [_from_bson(d) async for d in cursor]

    async def upsert(self, precedent_id: str, data: PrecedentBase, embedding: list[float] | None, embedding_model: str | None) -> PrecedentOut:
        doc = to_document(precedent_id, data, embedding, embedding_model)
        await self._coll.replace_one({"_id": precedent_id}, doc, upsert=True)
        return _from_bson(doc)
