from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import SessionLocal
from app.models import Link


def in_future(**delta):
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


def expire_now(code):
    with SessionLocal() as session:
        session.execute(
            update(Link).where(Link.code == code).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        session.commit()


def create(client, url="https://example.com/some/long/path", **extra):
    response = client.post("/api/links", json={"url": url, **extra})
    assert response.status_code == 201
    return response.json()


def stats(client, link):
    response = client.get(f"/api/links/{link['code']}", headers=auth(link))
    assert response.status_code == 200
    return response.json()


def auth(link):
    return {"Authorization": f"Bearer {link['manage_token']}"}


def run_worker():
    from app import redis_conn, worker

    worker.ensure_group(redis_conn.redis_client)
    total = 0
    while processed := worker.process_batch(redis_conn.redis_client, "test-worker", block_ms=None):
        total += processed
    return total
