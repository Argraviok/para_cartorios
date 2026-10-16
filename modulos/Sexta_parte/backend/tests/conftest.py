import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.core import config, database, storage


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("STORAGE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VLM_PROVIDER", "none")
    monkeypatch.setenv("API_TOKEN", "")
    config.get_settings.cache_clear()
    storage._fernet = None
    yield config.get_settings()
    config.get_settings.cache_clear()
    storage._fernet = None


@pytest.fixture
async def client(settings):
    from app.main import create_app

    db = AsyncMongoMockClient()["test"]
    await database.ensure_indexes(db)
    database.set_database(db)
    app = create_app(use_lifespan=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.db = db
        yield c
