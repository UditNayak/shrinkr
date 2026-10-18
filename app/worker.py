"""Background worker: reads click events from the Redis Stream and records them in Postgres:
the click counts (links.clicks) and the clicks per day (daily_clicks).

Run with:  python -m app.worker

Events are read through a consumer group, so several workers can share the stream and
each event goes to one of them. An event is acknowledged only after its clicks are saved;
if a worker dies mid-batch, another one claims its unacknowledged events. That means a
click is never lost, but in a rare crash it may be counted twice ("at-least-once").
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
BLOCK_MS = 1000  # wait up to 1 s for new events before looping
CLAIM_IDLE_MS = 60_000  # events unacknowledged this long belong to a crashed worker

log = logging.getLogger("shrinkr.worker")


def ensure_group(redis: Redis) -> None:
    """Create the consumer group if it doesn't exist (id="0": include events already queued)."""
    try:
        redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):  # BUSYGROUP = it already exists, which is fine
            raise


def _next_messages(redis: Redis, consumer: str, block_ms: int | None, claim_idle_ms: int):
    # 1. Events another worker received but never acknowledged (it crashed): take them over.
    _cursor, claimed, *_ = redis.xautoclaim(
        STREAM, GROUP, consumer, min_idle_time=claim_idle_ms, start_id="0-0", count=BATCH_SIZE
    )
    if claimed:
        return claimed
    # 2. New events (">"), waiting up to block_ms for some to arrive.
    response = redis.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=BATCH_SIZE, block=block_ms)
    return response[0][1] if response else []


def day_of(message_id: str) -> date:
    """The UTC day a click happened: a stream ID starts with milliseconds since 1970."""
    milliseconds = int(message_id.split("-")[0])
    return datetime.fromtimestamp(milliseconds / 1000, UTC).date()


def _add_daily_clicks(session: Session, daily: Counter) -> None:
    """Upsert: insert each (link, day) row, or add to its clicks if it already exists.

    One statement for the whole batch: INSERT ... ON CONFLICT (link_id, day) DO UPDATE SET
    clicks = clicks + excluded.clicks. Keys are unique within `daily` (Postgres refuses to
    update the same row twice in one statement), and sorted so workers lock in the same order.
    """
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
    """Count one batch of events into Postgres. Returns how many events were processed."""
    messages = _next_messages(redis, consumer, block_ms, claim_idle_ms)
    if not messages:
        return 0

    # Sum up the batch in memory first: 137 clicks on one link become one row update.
    clicks = Counter()  # code → clicks not yet in links.clicks
    daily = Counter()  # (code, day) → clicks
    for message_id, fields in messages:
        if not fields:  # deleted from the stream before we got to it
            continue
        code = fields["code"]
        if fields.get("counted") != "1":  # click-limited links were already counted
            clicks[code] += 1
        daily[code, day_of(message_id)] += 1

    with SessionLocal() as session:
        # Click counts and daily totals in ONE transaction: both are saved, or neither is.
        for code in sorted(clicks):  # sorted: concurrent workers lock rows in the same order
            session.execute(
                update(Link).where(Link.code == code).values(clicks=Link.clicks + clicks[code])
            )
        # daily_clicks refers to links by id. Links deleted meanwhile have no id any more,
        # so their events are dropped.
        codes = {code for code, _day in daily}
        link_ids = dict(session.execute(select(Link.code, Link.id).where(Link.code.in_(codes))).all())
        _add_daily_clicks(
            session,
            Counter({(link_ids[code], day): n for (code, day), n in daily.items() if code in link_ids}),
        )
        session.commit()

    # Only now, with everything safely in Postgres: acknowledge, and delete from the stream.
    ids = [message_id for message_id, _fields in messages]
    pipe = redis.pipeline()
    pipe.xack(STREAM, GROUP, *ids)
    pipe.xdel(STREAM, *ids)
    pipe.execute()
    return len(messages)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    # Its own connection: blocking reads (BLOCK_MS) need a longer timeout than the app's 0.5 s.
    redis = Redis.from_url(REDIS_URL, socket_timeout=5, socket_connect_timeout=2, decode_responses=True)
    consumer = f"{socket.gethostname()}-{os.getpid()}"

    # Graceful shutdown: on SIGTERM (docker stop, Kubernetes) finish the current batch, then exit.
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
                group_ready = False  # Redis lost the group (e.g. data wiped): recreate it
            log.warning("Batch failed (%s: %s); retrying in 1 s", type(exc).__name__, exc)
            stopping.wait(1)
    log.info("Worker %s stopped", consumer)


if __name__ == "__main__":
    main()
