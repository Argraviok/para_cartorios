"""Persistência de jobs e logs de auditoria.

Usa o driver assíncrono nativo do PyMongo (`AsyncMongoClient`), sucessor do Motor
(descontinuado em 2026). Sem `MONGODB_URI`, cai num repositório em memória,
útil para desenvolvimento local e testes.
"""

import copy
from typing import Any, Protocol

from pymongo import AsyncMongoClient, DESCENDING

from app.core.config import get_settings

JOBS = "redaction_jobs"
AUDIT = "lgpd_audit_logs"


class Repository(Protocol):
    async def insert_job(self, job: dict[str, Any]) -> None: ...
    async def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    async def update_job(self, job_id: str, fields: dict[str, Any]) -> None: ...
    async def list_jobs(self, limit: int) -> list[dict[str, Any]]: ...
    async def insert_audit(self, entry: dict[str, Any]) -> None: ...
    async def list_audit(self, job_id: str) -> list[dict[str, Any]]: ...
    async def close(self) -> None: ...


class MongoRepository:
    def __init__(self, uri: str, db_name: str):
        self._client: AsyncMongoClient = AsyncMongoClient(uri, tz_aware=True)
        self._db = self._client[db_name]

    async def init_indexes(self) -> None:
        await self._db[JOBS].create_index([("created_at", DESCENDING)])
        await self._db[AUDIT].create_index([("job_id", 1), ("timestamp", 1)])

    async def insert_job(self, job: dict[str, Any]) -> None:
        await self._db[JOBS].insert_one({"_id": job["job_id"], **job})

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return await self._db[JOBS].find_one({"_id": job_id}, {"_id": 0})

    async def update_job(self, job_id: str, fields: dict[str, Any]) -> None:
        await self._db[JOBS].update_one({"_id": job_id}, {"$set": fields})

    async def list_jobs(self, limit: int) -> list[dict[str, Any]]:
        cursor = self._db[JOBS].find({}, {"_id": 0, "items": 0, "pages": 0}).sort("created_at", DESCENDING).limit(limit)
        return await cursor.to_list()

    async def insert_audit(self, entry: dict[str, Any]) -> None:
        await self._db[AUDIT].insert_one({"_id": entry["audit_id"], **entry})

    async def list_audit(self, job_id: str) -> list[dict[str, Any]]:
        return await self._db[AUDIT].find({"job_id": job_id}, {"_id": 0}).sort("timestamp", 1).to_list()

    async def close(self) -> None:
        await self._client.close()


class InMemoryRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._audit: list[dict[str, Any]] = []

    async def insert_job(self, job: dict[str, Any]) -> None:
        self._jobs[job["job_id"]] = copy.deepcopy(job)

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        return copy.deepcopy(job) if job else None

    async def update_job(self, job_id: str, fields: dict[str, Any]) -> None:
        self._jobs[job_id].update(copy.deepcopy(fields))

    async def list_jobs(self, limit: int) -> list[dict[str, Any]]:
        jobs = sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)
        return [copy.deepcopy(j) for j in jobs[:limit]]

    async def insert_audit(self, entry: dict[str, Any]) -> None:
        self._audit.append(copy.deepcopy(entry))

    async def list_audit(self, job_id: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(e) for e in self._audit if e["job_id"] == job_id]

    async def close(self) -> None:
        pass


_repository: Repository | None = None


async def connect() -> Repository:
    global _repository
    settings = get_settings()
    if settings.mongodb_uri:
        repo = MongoRepository(settings.mongodb_uri, settings.mongodb_db)
        await repo.init_indexes()
        _repository = repo
    else:
        _repository = InMemoryRepository()
    return _repository


async def disconnect() -> None:
    global _repository
    if _repository is not None:
        await _repository.close()
        _repository = None


def get_repository() -> Repository:
    if _repository is None:
        raise RuntimeError("Repositório não inicializado")
    return _repository
