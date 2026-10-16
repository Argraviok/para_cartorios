from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings

PRECEDENTS = "legal_precedents"
NOTES = "devolution_notes"
COUNTERS = "counters"

VECTOR_INDEX = "precedents_vector"
TEXT_INDEX = "precedents_text"


def create_client(settings: Settings) -> AsyncMongoClient:
    return AsyncMongoClient(settings.mongodb_uri, tz_aware=True)


def get_database(client: AsyncMongoClient, settings: Settings) -> AsyncDatabase:
    return client[settings.mongodb_db]
