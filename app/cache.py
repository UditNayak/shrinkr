"""Cache of code → target URL in Redis, so most redirects never touch Postgres.

Only links without a click limit are cached: click-limited links need the exact database
path. An entry never outlives its link's expiry; edits and deletes remove it. Its lifetime
(CACHE_TTL_SECONDS) also caps how long a missed removal could serve a stale target.

Every function tolerates Redis being unavailable: a failed lookup is treated as a miss.
"""

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
    """The cached target URL, or None on a miss (or if Redis is unavailable)."""
    try:
        return redis_conn.redis_client.get(_key(code))
    except RedisError:
        log.warning("Redis unavailable; cache lookup skipped")
        return None


def store(code: str, target_url: str, expires_at: datetime | None) -> None:
    ttl = CACHE_TTL_SECONDS
    if expires_at is not None:
        if expires_at.tzinfo is None:  # SQLite (tests) returns naive datetimes, stored as UTC
            expires_at = expires_at.replace(tzinfo=UTC)
        # Never cache a link beyond the moment it expires.
        ttl = min(ttl, int((expires_at - datetime.now(UTC)).total_seconds()))
    if ttl <= 0:
        return
    try:
        redis_conn.redis_client.set(_key(code), target_url, ex=ttl)
    except RedisError:
        log.warning("Redis unavailable; %s not cached", code)


def invalidate(code: str) -> None:
    """Remove a link from the cache after it was changed or deleted."""
    try:
        redis_conn.redis_client.delete(_key(code))
    except RedisError:
        # The change is already saved in Postgres; the old entry expires within the TTL.
        log.error(
            "Redis unavailable; cached entry for %s may be stale for up to %d s",
            code,
            CACHE_TTL_SECONDS,
        )
