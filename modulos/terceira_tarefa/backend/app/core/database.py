import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
# Definido no startup: True quando o cluster suporta $search (Atlas ou atlas-local).
atlas_search_enabled: bool = False

# Analisador lucene.portuguese remove acentos/stemming; o campo fonético usa keyword
# por token (whitespace) para casar códigos fonéticos exatos.
SEARCH_INDEX_DEFINITION = {
    "mappings": {
        "dynamic": False,
        "fields": {
            "book_type": {"type": "token"},
            "status": {"type": "token"},
            "entry_date_iso": {"type": "token"},
            "entry_number": [{"type": "string", "analyzer": "lucene.keyword"}],
            "book_number": [{"type": "string", "analyzer": "lucene.keyword"}],
            "transcription_raw": {"type": "string", "analyzer": "lucene.portuguese"},
            "confrontants_or_relatives": {"type": "string", "analyzer": "lucene.portuguese"},
            "search_phonetic": {"type": "string", "analyzer": "lucene.whitespace"},
            "parties": {
                "type": "document",
                "fields": {
                    "name_standardized": {"type": "string", "analyzer": "lucene.standard"},
                    "name_original": {"type": "string", "analyzer": "lucene.standard"},
                    "role": {"type": "token"},
                },
            },
        },
    }
}


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_settings().mongo_uri, tz_aware=True)
    return _client


def get_collection() -> AsyncIOMotorCollection:
    s = get_settings()
    return get_client()[s.mongo_db][s.mongo_collection]


async def init_db() -> None:
    global atlas_search_enabled
    coll = get_collection()
    await coll.create_index([("book_type", ASCENDING), ("book_number", ASCENDING), ("page_number", ASCENDING)])
    await coll.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await coll.create_index("search_phonetic")
    await coll.create_index("entry_number")

    index_name = get_settings().atlas_search_index
    try:
        existing = [ix["name"] async for ix in coll.list_search_indexes()]
        if index_name not in existing:
            await coll.create_search_index(SearchIndexModel(definition=SEARCH_INDEX_DEFINITION, name=index_name))
            logger.info("Atlas Search index '%s' criado (pode levar alguns segundos para ficar READY).", index_name)
        atlas_search_enabled = True
    except OperationFailure as exc:
        atlas_search_enabled = False
        logger.warning("Atlas Search indisponível neste cluster; usando busca fonética/regex. (%s)", exc.details)


def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
