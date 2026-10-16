"""Cria (ou atualiza) os índices do projeto. Idempotente.

Uso: python -m scripts.create_indexes
"""

import asyncio

from pymongo import ASCENDING, DESCENDING
from pymongo.operations import SearchIndexModel

from app.core.config import get_settings
from app.core.database import NOTES, PRECEDENTS, TEXT_INDEX, VECTOR_INDEX, create_client, get_database


def vector_index_definition(dims: int) -> dict:
    return {
        "fields": [
            {"type": "vector", "path": "embedding", "numDimensions": dims, "similarity": "cosine"},
            {"type": "filter", "path": "vicio_code"},
            {"type": "filter", "path": "vigente"},
            {"type": "filter", "path": "scope"},
            {"type": "filter", "path": "uf"},
        ]
    }


TEXT_INDEX_DEFINITION = {
    "mappings": {
        "dynamic": False,
        "fields": {
            "title": {"type": "string", "analyzer": "lucene.portuguese"},
            "embedding_text": {"type": "string", "analyzer": "lucene.portuguese"},
            "normative_refs": {"type": "document", "fields": {"diploma": {"type": "string", "analyzer": "lucene.portuguese"}}},
            "vicio_code": {"type": "token"},
            "scope": {"type": "token"},
            "uf": {"type": "token"},
            "vigente": {"type": "boolean"},
        },
    }
}


async def ensure_indexes(db, dims: int) -> None:
    if PRECEDENTS not in await db.list_collection_names():
        await db.create_collection(PRECEDENTS)
    precedents = db[PRECEDENTS]

    existing = {idx["name"] async for idx in await precedents.list_search_indexes()}
    wanted = {
        VECTOR_INDEX: ("vectorSearch", vector_index_definition(dims)),
        TEXT_INDEX: ("search", TEXT_INDEX_DEFINITION),
    }
    for name, (kind, definition) in wanted.items():
        if name in existing:
            await precedents.update_search_index(name, definition)
            print(f"índice de busca '{name}' atualizado")
        else:
            await precedents.create_search_index(SearchIndexModel(definition=definition, name=name, type=kind))
            print(f"índice de busca '{name}' criado")

    notes = db[NOTES]
    await notes.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await notes.create_index([("protocol_number", ASCENDING)])
    await notes.create_index(
        [("note_number", ASCENDING)],
        unique=True,
        partialFilterExpression={"note_number": {"$type": "string"}},
    )
    print("índices de devolution_notes ok")


async def main() -> None:
    settings = get_settings()
    client = create_client(settings)
    try:
        await ensure_indexes(get_database(client, settings), settings.embedding_dims)
        print("Os índices de busca levam alguns segundos para ficarem consultáveis (status READY).")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
