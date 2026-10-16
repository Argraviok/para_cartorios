from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

client = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
db = client[settings.mongo_db]
