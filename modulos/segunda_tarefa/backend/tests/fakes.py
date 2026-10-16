import hashlib
import math
import re
from datetime import datetime, timezone

from bson import ObjectId
from pydantic import BaseModel

from app.repositories.notes import NoteConflict, NoteNotFound
from app.schemas.devolution_schema import DevolutionNote, LLMNoteDraft


class FakeLLM:
    """Devolve, em ordem, as respostas programadas e registra os prompts recebidos."""

    model = "fake-llm"

    def __init__(self, *responses: LLMNoteDraft | Exception):
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def generate_structured(self, system: str, user: str, schema: type[BaseModel]):
        self.prompts.append(user)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response, self.model


class FakeSearcher:
    def __init__(self, hits_by_code: dict[str, list[dict]]):
        self._hits = hits_by_code

    async def search(self, vicio_code, case_facts, uf, k=4):
        return self._hits.get(vicio_code.value, [])[:k]


class HashEmbedder:
    """Embedding determinístico por bag-of-words com hashing; só para testes."""

    model = "hash-embedder"

    def __init__(self, dims: int = 768):
        self._dims = dims

    async def embed(self, text: str, task: str) -> list[float]:
        vec = [0.0] * self._dims
        for token in re.findall(r"\w+", text.lower()):
            vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % self._dims] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


class InMemoryNoteRepository:
    """Mesma semântica do MongoNoteRepository; operações sem await internos são atômicas no event loop."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.counters: dict[int, int] = {}

    async def create(self, fields: dict) -> DevolutionNote:
        now = datetime.now(timezone.utc)
        note_id = str(ObjectId())
        self.docs[note_id] = {**fields, "id": note_id, "status": "draft", "note_number": None, "version": 1,
                              "created_at": now, "updated_at": now, "issued_at": None}
        return await self.get(note_id)

    async def get(self, note_id: str) -> DevolutionNote:
        if note_id not in self.docs:
            raise NoteNotFound(note_id)
        return DevolutionNote.model_validate(self.docs[note_id])

    async def update_draft(self, note_id, expected_version, fields):
        doc = self._require(note_id)
        if doc["status"] != "draft":
            raise NoteConflict("nota já emitida ou em emissão; não pode ser alterada")
        if doc["version"] != expected_version:
            raise NoteConflict("versão desatualizada")
        doc.update(fields, version=doc["version"] + 1, updated_at=datetime.now(timezone.utc))
        return await self.get(note_id)

    async def claim_for_issue(self, note_id):
        doc = self._require(note_id)
        if doc["status"] != "draft":
            raise NoteConflict("nota já emitida ou em emissão; não pode ser alterada")
        doc["status"] = "issuing"
        return await self.get(note_id)

    async def release_issue_claim(self, note_id):
        doc = self._require(note_id)
        if doc["status"] == "issuing":
            doc["status"] = "draft"

    async def next_number(self, year):
        self.counters[year] = self.counters.get(year, 0) + 1
        return self.counters[year]

    async def finalize_issue(self, note_id, fields):
        doc = self._require(note_id)
        if doc["status"] != "issuing":
            raise NoteConflict("emissão interrompida")
        now = datetime.now(timezone.utc)
        doc.update(fields, status="issued", issued_at=now, updated_at=now, version=doc["version"] + 1)
        return await self.get(note_id)

    def _require(self, note_id):
        if note_id not in self.docs:
            raise NoteNotFound(note_id)
        return self.docs[note_id]


def precedent(prec_id: str, vicio_code: str, refs: list[tuple[str, str | None]]) -> dict:
    return {
        "_id": prec_id,
        "vicio_code": vicio_code,
        "title": f"Ficha {prec_id}",
        "normative_refs": [{"diploma": d, "artigo": a} for d, a in refs],
        "jurisprudence": [],
        "recommended_text": "Redação-modelo.",
        "suggested_solution": "Providência padrão.",
    }
