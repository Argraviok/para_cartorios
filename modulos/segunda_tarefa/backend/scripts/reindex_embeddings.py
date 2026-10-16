"""Recalcula o embedding de todas as fichas com o modelo configurado.

Use após trocar EMBEDDING_PROVIDER/EMBEDDING_MODEL ou após um seed com --skip-embeddings.
Se EMBEDDING_DIMS mudar, rode também scripts.create_indexes.

Uso: python -m scripts.reindex_embeddings
"""

import asyncio

from app.core.config import get_settings
from app.core.database import PRECEDENTS, create_client, get_database
from app.services.embedding_service import build_embedder


async def main() -> None:
    settings = get_settings()
    embedder = build_embedder(settings)
    client = create_client(settings)
    coll = get_database(client, settings)[PRECEDENTS]
    count = 0
    try:
        async for doc in coll.find({}, {"embedding_text": 1}):
            vector = await embedder.embed(doc["embedding_text"], task="document")
            await coll.update_one({"_id": doc["_id"]}, {"$set": {"embedding": vector, "embedding_model": embedder.model}})
            count += 1
            print(f"  ✓ {doc['_id']}")
    finally:
        await client.close()
    print(f"\n{count} fichas reindexadas com {embedder.model} ({settings.embedding_dims} dimensões).")


if __name__ == "__main__":
    asyncio.run(main())
