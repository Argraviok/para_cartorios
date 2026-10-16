"""Acesso ao MongoDB Atlas (PyMongo Async — sucessor oficial do Motor).

Sem MONGODB_URI configurada, cai num repositório em memória para desenvolvimento local.
As escritas na triagem são atômicas por campo ($push / $set) para que mensagens do cidadão
e do escrevente chegando ao mesmo tempo não se sobrescrevam.
"""

import copy
import logging
from typing import Any, Optional, Protocol

from app.core.config import settings

log = logging.getLogger(__name__)

TRIAGES = "triages"
REQUIREMENTS = "act_requirements"
FEES = "fee_schedules"
COUNTERS = "counters"


class Repository(Protocol):
    async def insert_triage(self, doc: dict) -> None: ...
    async def get_triage(self, protocol_id: str) -> Optional[dict]: ...
    async def find_open_triage_by_contact(self, contact: str) -> Optional[dict]: ...
    async def set_triage_fields(self, protocol_id: str, fields: dict) -> None: ...
    async def push_messages(self, protocol_id: str, messages: list[dict], fields: dict) -> None: ...
    async def list_triages(self, status: Optional[str], limit: int) -> list[dict]: ...
    async def list_requirements(self) -> list[dict]: ...
    async def get_requirement(self, act_type: str) -> Optional[dict]: ...
    async def get_fee_schedule(self, state: str, service_type: str) -> Optional[dict]: ...
    async def list_fee_schedules(self, state: Optional[str]) -> list[dict]: ...
    async def replace_catalog(self, requirements: list[dict], fees: list[dict]) -> None: ...
    async def next_counter(self, name: str) -> int: ...


def _out(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


class MongoRepository:
    def __init__(self, uri: str) -> None:
        from pymongo import AsyncMongoClient

        self.client = AsyncMongoClient(uri, tz_aware=True)
        self.db = self.client[settings.mongodb_db]

    async def ensure_indexes(self) -> None:
        t = self.db[TRIAGES]
        await t.create_index([("status", 1), ("updated_at", -1)])
        await t.create_index([("customer_contact", 1), ("status", 1)])
        await self.db[REQUIREMENTS].create_index("act_type", unique=True)
        await self.db[FEES].create_index([("state", 1), ("service_type", 1)], unique=True)

    async def insert_triage(self, doc: dict) -> None:
        await self.db[TRIAGES].insert_one({**doc, "_id": doc["protocol_id"]})

    async def get_triage(self, protocol_id: str) -> Optional[dict]:
        return _out(await self.db[TRIAGES].find_one({"_id": protocol_id}))

    async def find_open_triage_by_contact(self, contact: str) -> Optional[dict]:
        return _out(
            await self.db[TRIAGES].find_one(
                {"customer_contact": contact, "stage": {"$ne": "done"}}, sort=[("updated_at", -1)]
            )
        )

    async def set_triage_fields(self, protocol_id: str, fields: dict) -> None:
        await self.db[TRIAGES].update_one({"_id": protocol_id}, {"$set": fields})

    async def push_messages(self, protocol_id: str, messages: list[dict], fields: dict) -> None:
        update: dict[str, Any] = {"$push": {"chat_history": {"$each": messages}}}
        if fields:
            update["$set"] = fields
        await self.db[TRIAGES].update_one({"_id": protocol_id}, update)

    async def list_triages(self, status: Optional[str], limit: int) -> list[dict]:
        query = {"status": status} if status else {}
        cursor = self.db[TRIAGES].find(query).sort("updated_at", -1).limit(limit)
        return [_out(d) async for d in cursor]

    async def list_requirements(self) -> list[dict]:
        return [_out(d) async for d in self.db[REQUIREMENTS].find().sort("name", 1)]

    async def get_requirement(self, act_type: str) -> Optional[dict]:
        return _out(await self.db[REQUIREMENTS].find_one({"act_type": act_type}))

    async def get_fee_schedule(self, state: str, service_type: str) -> Optional[dict]:
        # fee_schedules mantém o _id (identifica a versão da tabela)
        return await self.db[FEES].find_one({"state": state, "service_type": service_type})

    async def list_fee_schedules(self, state: Optional[str]) -> list[dict]:
        return [d async for d in self.db[FEES].find({"state": state} if state else {})]

    async def replace_catalog(self, requirements: list[dict], fees: list[dict]) -> None:
        await self.db[REQUIREMENTS].delete_many({})
        await self.db[FEES].delete_many({})
        if requirements:
            await self.db[REQUIREMENTS].insert_many([{**r, "_id": r["act_type"]} for r in requirements])
        if fees:
            await self.db[FEES].insert_many(copy.deepcopy(fees))

    async def next_counter(self, name: str) -> int:
        doc = await self.db[COUNTERS].find_one_and_update(
            {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
        )
        return int(doc["seq"])


class InMemoryRepository:
    def __init__(self) -> None:
        self.triages: dict[str, dict] = {}
        self.requirements: dict[str, dict] = {}
        self.fees: list[dict] = []
        self.counters: dict[str, int] = {}

    async def ensure_indexes(self) -> None:
        pass

    async def insert_triage(self, doc: dict) -> None:
        self.triages[doc["protocol_id"]] = copy.deepcopy(doc)

    async def get_triage(self, protocol_id: str) -> Optional[dict]:
        return copy.deepcopy(self.triages.get(protocol_id))

    async def find_open_triage_by_contact(self, contact: str) -> Optional[dict]:
        hits = [t for t in self.triages.values() if t["customer_contact"] == contact and t["stage"] != "done"]
        hits.sort(key=lambda t: t["updated_at"], reverse=True)
        return copy.deepcopy(hits[0]) if hits else None

    async def set_triage_fields(self, protocol_id: str, fields: dict) -> None:
        doc = self.triages[protocol_id]
        for key, value in copy.deepcopy(fields).items():
            # Suporta caminhos "checklist.2" como o $set do Mongo
            parts = key.split(".")
            target: Any = doc
            for p in parts[:-1]:
                target = target[int(p)] if isinstance(target, list) else target[p]
            last = parts[-1]
            if isinstance(target, list):
                target[int(last)] = value
            else:
                target[last] = value

    async def push_messages(self, protocol_id: str, messages: list[dict], fields: dict) -> None:
        self.triages[protocol_id]["chat_history"].extend(copy.deepcopy(messages))
        if fields:
            await self.set_triage_fields(protocol_id, fields)

    async def list_triages(self, status: Optional[str], limit: int) -> list[dict]:
        docs = [t for t in self.triages.values() if not status or t["status"] == status]
        docs.sort(key=lambda t: t["updated_at"], reverse=True)
        return copy.deepcopy(docs[:limit])

    async def list_requirements(self) -> list[dict]:
        return copy.deepcopy(sorted(self.requirements.values(), key=lambda r: r["name"]))

    async def get_requirement(self, act_type: str) -> Optional[dict]:
        return copy.deepcopy(self.requirements.get(act_type))

    async def get_fee_schedule(self, state: str, service_type: str) -> Optional[dict]:
        for f in self.fees:
            if f["state"] == state and f["service_type"] == service_type:
                return copy.deepcopy(f)
        return None

    async def list_fee_schedules(self, state: Optional[str]) -> list[dict]:
        return copy.deepcopy([f for f in self.fees if not state or f["state"] == state])

    async def replace_catalog(self, requirements: list[dict], fees: list[dict]) -> None:
        self.requirements = {r["act_type"]: copy.deepcopy(r) for r in requirements}
        self.fees = copy.deepcopy(fees)

    async def next_counter(self, name: str) -> int:
        self.counters[name] = self.counters.get(name, 0) + 1
        return self.counters[name]


_repo: Optional[Any] = None


async def init_repository() -> None:
    global _repo
    if settings.mongodb_uri:
        _repo = MongoRepository(settings.mongodb_uri)
        log.info("Usando MongoDB (%s)", settings.mongodb_db)
    else:
        _repo = InMemoryRepository()
        log.warning("MONGODB_URI não definida — usando repositório em memória (dados não persistem)")
    await _repo.ensure_indexes()
    # O catálogo (atos + emolumentos) é semeado automaticamente se estiver vazio
    if not await _repo.list_requirements():
        from app.catalog import ACT_REQUIREMENTS, FEE_SCHEDULES

        await _repo.replace_catalog(ACT_REQUIREMENTS, FEE_SCHEDULES)
        log.info("Catálogo de atos e emolumentos semeado (%d atos)", len(ACT_REQUIREMENTS))


def set_repository(repo: Any) -> None:
    global _repo
    _repo = repo


def get_repository() -> Repository:
    if _repo is None:
        raise RuntimeError("Repositório não inicializado")
    return _repo
