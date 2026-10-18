import os
import tempfile

# Must be set before the app is imported: the database engine is created at import time.
# Tests use a throwaway SQLite file unless TEST_DATABASE_URL points at a real Postgres.
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
    # Build the schema exactly the way production does: by running the migrations.
    command.upgrade(alembic_config, "head")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Every test gets its own empty in-memory Redis, so counters never leak between tests.

    Returns the fake *server*: set `.connected = False` on it to simulate Redis being down.
    """
    server = fakeredis.FakeServer()
    monkeypatch.setattr(redis_conn, "redis_client", fakeredis.FakeRedis(server=server, decode_responses=True))
    return server
