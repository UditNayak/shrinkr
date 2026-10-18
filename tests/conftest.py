import os
import tempfile

# Set before importing the app: the engine is created at import time.
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db"
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import redis_conn  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def alembic_config():
    return Config("alembic.ini")


@pytest.fixture(scope="session", autouse=True)
def migrated_database(alembic_config):
    command.upgrade(alembic_config, "head")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(redis_conn, "redis_client", fakeredis.FakeRedis(server=server, decode_responses=True))
    return server
