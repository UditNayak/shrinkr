import pytest
from sqlalchemy.exc import OperationalError

from app import events, redis_conn, worker
from tests.helpers import create, run_worker, stats


def redis():
    return redis_conn.redis_client


def queue_clicks(code, n):
    for _ in range(n):
        events.record_click(code)


def test_counts_and_acknowledges_clicks(client):
    a, b = create(client), create(client)
    queue_clicks(a["code"], 3)
    queue_clicks(b["code"], 2)

    assert run_worker() == 5
    assert (stats(client, a)["clicks"], stats(client, b)["clicks"]) == (3, 2)
    assert redis().xlen(events.STREAM) == 0


def test_takes_over_a_crashed_workers_clicks(client):
    link = create(client)
    queue_clicks(link["code"], 3)
    worker.ensure_group(redis())
    # worker-a reads the events and "crashes" before acknowledging them
    redis().xreadgroup(worker.GROUP, "worker-a", {events.STREAM: ">"}, count=10)

    assert worker.process_batch(redis(), "worker-b", block_ms=None, claim_idle_ms=0) == 3
    assert stats(client, link)["clicks"] == 3


def test_database_failure_loses_no_clicks(client, monkeypatch):
    link = create(client)
    queue_clicks(link["code"], 2)
    worker.ensure_group(redis())

    def broken_session():
        raise OperationalError("UPDATE", {}, Exception("database is down"))

    with monkeypatch.context() as patch:
        patch.setattr(worker, "SessionLocal", broken_session)
        with pytest.raises(OperationalError):
            worker.process_batch(redis(), "worker-a", block_ms=None)

    assert worker.process_batch(redis(), "worker-b", block_ms=None, claim_idle_ms=0) == 2
    assert stats(client, link)["clicks"] == 2
