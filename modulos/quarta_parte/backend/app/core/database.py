"""Acesso ao MongoDB Atlas via Motor.

Sem MONGODB_URI configurada, cai num repositório em memória para desenvolvimento local.
"""

import logging
from typing import Any, Optional, Protocol

from bson import ObjectId

from app.core.config import settings

log = logging.getLogger(__name__)


class Repository(Protocol):
    async def insert(self, doc: dict) -> str: ...
    async def get(self, analysis_id: str) -> Optional[dict]: ...
    async def update(self, analysis_id: str, fields: dict) -> None: ...
    async def list_recent(self, limit: int) -> list[dict]: ...
    async def find_overlaps(self, geojson: dict, exclude_registry: str) -> list[dict]: ...


class MongoRepository:
    def __init__(self, uri: str) -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        self.client = AsyncIOMotorClient(uri)
        self.col = self.client[settings.mongodb_db][settings.mongodb_collection]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("geometry.location_geojson", "2dsphere")], sparse=True)
        await self.col.create_index("registry_number")
        await self.col.create_index([("created_at", -1)])

    async def insert(self, doc: dict) -> str:
        res = await self.col.insert_one(doc)
        return str(res.inserted_id)

    async def update(self, analysis_id: str, fields: dict) -> None:
        await self.col.update_one({"_id": ObjectId(analysis_id)}, {"$set": fields})

    async def get(self, analysis_id: str) -> Optional[dict]:
        if not ObjectId.is_valid(analysis_id):
            return None
        return _out(await self.col.find_one({"_id": ObjectId(analysis_id)}))

    async def list_recent(self, limit: int) -> list[dict]:
        cursor = self.col.find(
            {},
            {"registry_number": 1, "registry_office": 1, "subjective_continuity.status": 1,
             "created_at": 1, "document_filename": 1},
        ).sort("created_at", -1).limit(limit)
        return [_out(d) async for d in cursor]

    async def find_overlaps(self, geojson: dict, exclude_registry: str) -> list[dict]:
        cursor = self.col.find(
            {
                "registry_number": {"$ne": exclude_registry},
                "geometry.location_geojson": {"$geoIntersects": {"$geometry": geojson}},
            },
            {"registry_number": 1, "geometry.location_geojson": 1},
        ).limit(20)
        return [_out(d) async for d in cursor]


class InMemoryRepository:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    async def ensure_indexes(self) -> None:
        pass

    async def insert(self, doc: dict) -> str:
        oid = str(ObjectId())
        self.docs[oid] = {**doc, "_id": oid}
        return oid

    async def update(self, analysis_id: str, fields: dict) -> None:
        self.docs[analysis_id].update(fields)

    async def get(self, analysis_id: str) -> Optional[dict]:
        return _out(self.docs.get(analysis_id))

    async def list_recent(self, limit: int) -> list[dict]:
        docs = sorted(self.docs.values(), key=lambda d: d["created_at"], reverse=True)
        return [_out(d) for d in docs[:limit]]

    async def find_overlaps(self, geojson: dict, exclude_registry: str) -> list[dict]:
        from shapely.geometry import shape

        target = shape(geojson)
        hits = []
        for d in self.docs.values():
            other = (d.get("geometry") or {}).get("location_geojson")
            if other and d["registry_number"] != exclude_registry and shape(other).intersects(target):
                hits.append(_out(d))
        return hits


def _out(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


_repo: Optional[Any] = None


async def init_repository() -> None:
    global _repo
    if settings.mongodb_uri:
        _repo = MongoRepository(settings.mongodb_uri)
        log.info("Usando MongoDB Atlas (%s.%s)", settings.mongodb_db, settings.mongodb_collection)
    else:
        _repo = InMemoryRepository()
        log.warning("MONGODB_URI não definida — usando repositório em memória (dados não persistem)")
    await _repo.ensure_indexes()


def get_repository() -> Repository:
    if _repo is None:
        raise RuntimeError("Repositório não inicializado")
    return _repo
