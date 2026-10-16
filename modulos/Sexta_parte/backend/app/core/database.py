from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect() -> None:
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri, uuidRepresentation="standard", tz_aware=True)
    _db = _client[settings.mongodb_db]
    await ensure_indexes(_db)


async def disconnect() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def set_database(db: AsyncIOMotorDatabase) -> None:
    """Permite injetar um banco (ex.: mongomock nos testes)."""
    global _db
    _db = db


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Banco de dados não inicializado")
    return _db


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.signature_cards.create_index("cpf", unique=True)
    await db.fraud_audits.create_index("protocol_number")
    await db.fraud_audits.create_index([("created_at", -1)])
    await db.fraud_audits.create_index("presenter_cpf")
    await db.suspicious_patterns.create_index("cpf")
