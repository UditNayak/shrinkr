"""Counts queued click events into Postgres (links.clicks and daily_clicks).

Usage: python -m app.worker

Events are acknowledged only after they are saved, and events left unacknowledged by a
crashed worker are claimed by another one: clicks are never lost, but may rarely be
counted twice.
"""

import logging
import os
import signal
import socket
import threading
from collections import Counter
from datetime import UTC, date, datetime

from redis import Redis
from redis.exceptions import RedisError, ResponseError
from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import SessionLocal
from .events import STREAM
from .models import DailyClicks, Link
from .redis_conn import REDIS_URL

GROUP = "click-counters"
BATCH_SIZE = 500
BLOCK_MS = 1000
CLAIM_IDLE_MS = 60_000

log = logging.getLogger("shrinkr.worker")


def ensure_group(redis: Redis) -> None:
    try:
        # id="0" so events queued before the group existed are counted too
        redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _next_messages(redis: Redis, consumer: str, block_ms: int | None, claim_idle_ms: int):
    # first take over events a crashed worker never acknowledged
    _cursor, claimed, *_ = redis.xautoclaim(
        STREAM, GROUP, consumer, min_idle_time=claim_idle_ms, start_id="0-0", count=BATCH_SIZE
    )
    if claimed:
        return claimed
    response = redis.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=BATCH_SIZE, block=block_ms)
    return response[0][1] if response else []


def day_of(message_id: str) -> date:
    milliseconds = int(message_id.split("-")[0])
    return datetime.fromtimestamp(milliseconds / 1000, UTC).date()


def _add_daily_clicks(session: Session, daily: Counter) -> None:
    if not daily:
        return
    rows = [{"link_id": link_id, "day": day, "clicks": n} for (link_id, day), n in sorted(daily.items())]
    dialect = postgresql if session.get_bind().dialect.name == "postgresql" else sqlite
    statement = dialect.insert(DailyClicks).values(rows)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["link_id", "day"],
            set_={"clicks": DailyClicks.clicks + statement.excluded.clicks},
        )
    )


def process_batch(
    redis: Redis,
    consumer: str,
    block_ms: int | None = BLOCK_MS,
    claim_idle_ms: int = CLAIM_IDLE_MS,
) -> int:
    messages = _next_messages(redis, consumer, block_ms, claim_idle_ms)
    if not messages:
        return 0

    clicks = Counter()
    daily = Counter()
    for message_id, fields in messages:
        if not fields:
            continue
        code = fields["code"]
        if fields.get("counted") != "1":  # click-limited links are counted by the redirect
            clicks[code] += 1
        daily[code, day_of(message_id)] += 1

    with SessionLocal() as session:
        # Sorted so that concurrent workers lock rows in the same order (no deadlocks).
        for code in sorted(clicks):
            session.execute(
                update(Link).where(Link.code == code).values(clicks=Link.clicks + clicks[code])
            )
        codes = {code for code, _day in daily}
        link_ids = dict(session.execute(select(Link.code, Link.id).where(Link.code.in_(codes))).all())
        _add_daily_clicks(
            session,
            Counter({(link_ids[code], day): n for (code, day), n in daily.items() if code in link_ids}),
        )
        session.commit()

    # acknowledge only after the commit, so a crash can't lose clicks
    ids = [message_id for message_id, _fields in messages]
    pipe = redis.pipeline()
    pipe.xack(STREAM, GROUP, *ids)
    pipe.xdel(STREAM, *ids)
    pipe.execute()
    return len(messages)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Longer timeout than the app's: XREADGROUP blocks for up to BLOCK_MS.
    redis = Redis.from_url(REDIS_URL, socket_timeout=5, socket_connect_timeout=2, decode_responses=True)
    consumer = f"{socket.gethostname()}-{os.getpid()}"

    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())

    log.info("Worker %s started", consumer)
    group_ready = False
    while not stopping.is_set():
        try:
            if not group_ready:
                ensure_group(redis)
                group_ready = True
            processed = process_batch(redis, consumer)
            if processed:
                log.info("Counted %d click event(s)", processed)
        except (RedisError, SQLAlchemyError) as exc:
            if isinstance(exc, ResponseError) and "NOGROUP" in str(exc):
                group_ready = False
            log.warning("Batch failed (%s: %s), retrying", type(exc).__name__, exc)
            stopping.wait(1)
    log.info("Worker %s stopped", consumer)


if __name__ == "__main__":
    main()
