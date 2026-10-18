import logging
import os
from datetime import UTC, datetime

from redis.exceptions import RedisError

from . import redis_conn

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))

log = logging.getLogger("shrinkr.cache")


def _key(code: str) -> str:
    return f"link:{code}"


def get_target(code: str) -> str | None:
    try:
        return redis_conn.redis_client.get(_key(code))
    except RedisError:
        log.warning("Redis unavailable, cache lookup skipped")
        return None


def store(code: str, target_url: str, expires_at: datetime | None) -> None:
    ttl = CACHE_TTL_SECONDS
    if expires_at is not None:
        if expires_at.tzinfo is None:  # SQLite returns naive datetimes
            expires_at = expires_at.replace(tzinfo=UTC)
        # never cache past the link's expiry
        ttl = min(ttl, int((expires_at - datetime.now(UTC)).total_seconds()))
    if ttl <= 0:
        return
    try:
        redis_conn.redis_client.set(_key(code), target_url, ex=ttl)
    except RedisError:
        log.warning("Redis unavailable, %s not cached", code)


def invalidate(code: str) -> None:
    try:
        redis_conn.redis_client.delete(_key(code))
    except RedisError:
        # already saved in Postgres, the old entry expires within the TTL
        log.error("Redis unavailable, cache entry for %s may be stale", code)
