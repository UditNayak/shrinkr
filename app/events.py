import logging

from redis.exceptions import RedisError

from . import redis_conn

STREAM = "clicks"
MAX_STREAM_LENGTH = 1_000_000  # caps memory if the worker falls far behind

log = logging.getLogger("shrinkr.events")


def record_click(code: str, counted: bool = False) -> bool:
    """Queue a click for the worker. Returns False if Redis is unavailable.

    counted=True: the click is already in links.clicks, only the daily total is missing.
    """
    fields = {"code": code}
    if counted:
        fields["counted"] = "1"
    try:
        redis_conn.redis_client.xadd(STREAM, fields, maxlen=MAX_STREAM_LENGTH, approximate=True)
        return True
    except RedisError:
        log.warning("Redis unavailable, click on %s not queued", code)
        return False
