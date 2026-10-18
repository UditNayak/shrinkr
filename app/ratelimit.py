"""Per-client rate limits, counted in Redis so that every app instance shares them.

Fixed-window algorithm: one counter per client per minute. Simple and cheap; its known
weakness is that a client can squeeze up to 2x the limit around a window boundary
(the end of one minute plus the start of the next).
"""

import logging
import os
import time

from fastapi import HTTPException, Request
from redis.exceptions import RedisError

from . import redis_conn

WINDOW_SECONDS = 60

log = logging.getLogger("shrinkr.ratelimit")


class RateLimit:
    """FastAPI dependency allowing `limit` requests per client IP per minute."""

    def __init__(self, name: str, limit: int):
        self.name = name  # separate counters per group of routes
        self.limit = limit

    def __call__(self, request: Request) -> None:
        now = int(time.time())
        client = request.client.host if request.client else "unknown"
        key = f"ratelimit:{self.name}:{client}:{now // WINDOW_SECONDS}"

        try:
            # A pipeline sends both commands together in one MULTI/EXEC transaction, so the
            # counter can't be left without an expiry. NX: set the expiry only on the first hit.
            pipe = redis_conn.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, WINDOW_SECONDS, nx=True)
            count, _ = pipe.execute()
        except RedisError:
            # Fail open: rate limiting protects the service but isn't its core job, so a
            # Redis outage shouldn't stop people using shrinkr.
            log.warning("Redis unavailable; rate limit '%s' not enforced", self.name)
            return

        if count > self.limit:
            raise HTTPException(
                status_code=429,
                detail="Too many requests, please slow down",
                headers={"Retry-After": str(WINDOW_SECONDS - now % WINDOW_SECONDS)},
            )


create_limit = RateLimit("create", int(os.getenv("RATE_LIMIT_CREATE_PER_MINUTE", "10")))
manage_limit = RateLimit("manage", int(os.getenv("RATE_LIMIT_MANAGE_PER_MINUTE", "60")))
qr_limit = RateLimit("qr", int(os.getenv("RATE_LIMIT_QR_PER_MINUTE", "60")))
