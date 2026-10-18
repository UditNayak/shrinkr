"""Click events: a redirect appends one to a Redis Stream; the worker counts them later.

A Redis Stream is an append-only log of messages. Writing one is a single fast Redis
command, so redirects don't wait for a database write.
"""

import logging

from redis.exceptions import RedisError

from . import redis_conn

STREAM = "clicks"
# Safety cap on memory. The worker deletes events once counted, so the stream only holds
# the backlog; the oldest events are dropped only if the backlog grew past this.
MAX_STREAM_LENGTH = 1_000_000

log = logging.getLogger("shrinkr.events")


def record_click(code: str, counted: bool = False) -> bool:
    """Queue a click. Returns False if Redis is unavailable (the caller counts it directly).

    counted=True means the click was already added to links.clicks (click-limited links),
    so the worker only adds it to the daily totals.
    """
    fields = {"code": code}
    if counted:
        fields["counted"] = "1"
    try:
        # approximate=True ("MAXLEN ~"): Redis trims in efficient chunks instead of exactly.
        redis_conn.redis_client.xadd(STREAM, fields, maxlen=MAX_STREAM_LENGTH, approximate=True)
        return True
    except RedisError:
        if counted:
            log.warning("Redis unavailable; analytics for a click on %s not recorded", code)
        else:
            log.warning("Redis unavailable; click on %s counted directly in the database", code)
        return False
