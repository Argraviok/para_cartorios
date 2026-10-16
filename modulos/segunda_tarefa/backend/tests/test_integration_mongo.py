"""Integração com MongoDB real (imagem mongodb/mongodb-atlas-local, que tem Vector Search e Atlas Search).

Usa um banco descartável. É pulado se o Mongo não estiver acessível.
Configurar com TEST_MONGODB_URI (padrão: mongodb://localhost:27018/?directConnection=true).
"""

import asyncio
import os
import uuid
from datetime import date

import pytest
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.core.database import PRECEDENTS
from app.repositories.notes import MongoNoteRepository, NoteConflict
from app.repositories.precedents import MongoPrecedentRepository
from app.schemas.enums import VicioCode
from app.services.search_service import MongoHybridSearcher
from scripts.create_indexes import ensure_indexes
from scripts.seed_precedents import SEED, seed
from tests.fakes import HashEmbedder

URI = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27018/?directConnection=true")
pytestmark = pytest.mark.integration


@pytest.fixture
async def db():
    client = AsyncMongoClient(URI, tz_aware=True, serverSelectionTimeoutMS=2000)
    try:
        await client.admin.command("ping")
    except PyMongoError:
        await client.close()
        pytest.skip(f"MongoDB indisponível em {URI}")
    name = f"notas_test_{uuid.uuid4().hex[:8]}"
    database = client[name]
    yield database
    await client.drop_database(name)
    await client.close()


NOTE_FIELDS = {
    "protocol_number": "1", "protocol_date": date(2026, 10, 14), "act_type": "x", "presenter_name": "y",
    "uf": "SP", "requirements": [], "full_compiled_text": "", "llm_model": None, "prompt_version": "v1",
}


async def test_concurrent_issue_numbers_are_distinct_and_sequential(db):
    repo = MongoNoteRepository(db)
    notes = [await repo.create(NOTE_FIELDS) for _ in range(10)]

    async def issue(note_id):
        await repo.claim_for_issue(note_id)
        seq = await repo.next_number(2026)
        return await repo.finalize_issue(note_id, {"note_number": f"{seq}/2026"})

    issued = await asyncio.gather(*(issue(n.id) for n in notes))
    numbers = sorted(int(n.note_number.split("/")[0]) for n in issued)
    assert numbers == list(range(1, 11))


async def test_same_note_issued_concurrently_only_once(db):
    repo = MongoNoteRepository(db)
    note = await repo.create(NOTE_FIELDS)
    results = await asyncio.gather(*(repo.claim_for_issue(note.id) for _ in range(5)), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert all(isinstance(r, NoteConflict) for r in results if isinstance(r, Exception))


async def test_optimistic_version_and_dates_roundtrip(db):
    repo = MongoNoteRepository(db)
    note = await repo.create(NOTE_FIELDS)
    assert note.protocol_date == date(2026, 10, 14)
    updated = await repo.update_draft(note.id, 1, {"full_compiled_text": "novo"})
    assert updated.version == 2
    with pytest.raises(NoteConflict, match="versão"):
        await repo.update_draft(note.id, 1, {"full_compiled_text": "conflito"})


async def _wait_search_ready(db, timeout: float = 60):
    coll = db[PRECEDENTS]
    for _ in range(int(timeout * 2)):
        indexes = [i async for i in await coll.list_search_indexes()]
        if indexes and all(i.get("queryable") for i in indexes):
            return
        await asyncio.sleep(0.5)
    pytest.fail("índices de busca não ficaram prontos")


async def test_hybrid_search_on_seeded_precedents(db):
    embedder = HashEmbedder(768)
    await ensure_indexes(db, 768)
    await seed(MongoPrecedentRepository(db), embedder)
    await _wait_search_ready(db)
    searcher = MongoHybridSearcher(db, embedder)

    async def search_until_found(code, facts, uf):
        for _ in range(40):  # o índice é eventualmente consistente após a escrita
            hits = await searcher.search(code, facts, uf=uf)
            if hits:
                return hits
            await asyncio.sleep(0.5)
        return []

    hits = await search_until_found(
        VicioCode.OUTORGA_CONJUGAL, "Alienante casado no regime da comunhão parcial sem anuência do cônjuge.", "SP"
    )
    assert [h["_id"] for h in hits] == ["prec_outorga_conjugal_01"]
    assert "embedding" not in hits[0]

    # Filtro por vício: nenhuma ficha de outro vício vaza
    hits = await search_until_found(VicioCode.ITBI_NAO_RECOLHIDO, "Guia de ITBI não apresentada.", "MG")
    assert {h["vicio_code"] for h in hits} == {"itbi_nao_recolhido"}

    # Cada metade da busca funciona sozinha
    vec = await searcher._vector_search(VicioCode.QUEBRA_CONTINUIDADE, "transmitente diverso do titular", "SP")
    txt = await searcher._text_search(VicioCode.QUEBRA_CONTINUIDADE, "transmitente diverso do titular", "SP")
    assert [h["_id"] for h in vec] == [h["_id"] for h in txt] == ["prec_quebra_continuidade_01"]


async def test_state_scoped_precedent_respects_uf(db):
    embedder = HashEmbedder(768)
    await ensure_indexes(db, 768)
    await seed(MongoPrecedentRepository(db), embedder)
    data = SEED["prec_procuracao_sem_censec_01"].model_copy(update={"scope": "estadual", "uf": "SP", "title": "Regra estadual SP"})
    await MongoPrecedentRepository(db).upsert("prec_procuracao_sp_01", data, await embedder.embed(data.build_embedding_text(), "document"), embedder.model)
    await _wait_search_ready(db)
    searcher = MongoHybridSearcher(db, embedder)
    facts = "Procuração lavrada há mais de 90 dias sem certidão da CENSEC."

    async def ids_for(uf):
        for _ in range(40):
            hits = await searcher.search(VicioCode.PROCURACAO_SEM_CENSEC, facts, uf=uf)
            if len(hits) >= (2 if uf == "SP" else 1):
                return {h["_id"] for h in hits}
            await asyncio.sleep(0.5)
        return {h["_id"] for h in hits}

    assert await ids_for("SP") == {"prec_procuracao_sem_censec_01", "prec_procuracao_sp_01"}
    assert await ids_for("RJ") == {"prec_procuracao_sem_censec_01"}
