import asyncio
import logging
from typing import Protocol

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure

from app.core.database import PRECEDENTS, TEXT_INDEX, VECTOR_INDEX
from app.schemas.enums import VicioCode
from app.services.embedding_service import Embedder

log = logging.getLogger(__name__)

RRF_K = 60
CANDIDATES_PER_LIST = 10


class PrecedentSearcher(Protocol):
    async def search(self, vicio_code: VicioCode, case_facts: str, uf: str, k: int = 4) -> list[dict]: ...


def rrf_merge(ranked_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion: score = Σ 1/(k + rank), rank começando em 1. Deduplica por _id."""
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            doc_id = doc["_id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            docs.setdefault(doc_id, doc)
    return [docs[i] for i in sorted(scores, key=lambda i: scores[i], reverse=True)]


class MongoHybridSearcher:
    def __init__(self, db: AsyncDatabase, embedder: Embedder | None):
        self._coll = db[PRECEDENTS]
        self._embedder = embedder

    async def search(self, vicio_code: VicioCode, case_facts: str, uf: str, k: int = 4) -> list[dict]:
        vector_hits, text_hits = await asyncio.gather(
            self._vector_search(vicio_code, case_facts, uf),
            self._text_search(vicio_code, case_facts, uf),
        )
        return rrf_merge([vector_hits, text_hits])[:k]

    async def _vector_search(self, vicio_code: VicioCode, case_facts: str, uf: str) -> list[dict]:
        if self._embedder is None:
            return []
        try:
            query_vector = await self._embedder.embed(case_facts, task="query")
        except Exception as exc:  # falha do provedor não deve derrubar a busca textual
            log.warning("Embedding da consulta falhou: %s", exc)
            return []
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": 100,
                    "limit": CANDIDATES_PER_LIST,
                    "filter": {
                        "$and": [
                            {"vicio_code": vicio_code.value},
                            {"vigente": True},
                            {"$or": [{"scope": "nacional"}, {"uf": uf}]},
                        ]
                    },
                }
            },
            {"$project": {"embedding": 0}},
        ]
        return await self._run(pipeline, "vector")

    async def _text_search(self, vicio_code: VicioCode, case_facts: str, uf: str) -> list[dict]:
        pipeline = [
            {
                "$search": {
                    "index": TEXT_INDEX,
                    "compound": {
                        "should": [
                            {"text": {"query": case_facts, "path": ["title", "embedding_text", "normative_refs.diploma"]}}
                        ],
                        "filter": [
                            {"equals": {"path": "vicio_code", "value": vicio_code.value}},
                            {"equals": {"path": "vigente", "value": True}},
                            {
                                "compound": {
                                    "should": [
                                        {"equals": {"path": "scope", "value": "nacional"}},
                                        {"equals": {"path": "uf", "value": uf}},
                                    ],
                                    "minimumShouldMatch": 1,
                                }
                            },
                        ],
                    },
                }
            },
            {"$limit": CANDIDATES_PER_LIST},
            {"$project": {"embedding": 0}},
        ]
        return await self._run(pipeline, "text")

    async def _run(self, pipeline: list[dict], kind: str) -> list[dict]:
        try:
            cursor = await self._coll.aggregate(pipeline)
            return await cursor.to_list()
        except OperationFailure as exc:
            # Índice ausente ou ainda em construção: degrada para a outra metade da busca
            log.warning("Busca %s indisponível: %s", kind, exc)
            return []
