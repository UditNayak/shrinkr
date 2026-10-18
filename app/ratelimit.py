import logging
import os
import time

from fastapi import HTTPException, Request
from redis.exceptions import RedisError

from . import redis_conn

WINDOW_SECONDS = 60

log = logging.getLogger("shrinkr.ratelimit")


class RateLimit:
    """Fixed-window limit per client IP, counted in Redis."""

    def __init__(self, name: str, limit: int):
        self.name = name
        self.limit = limit

    def __call__(self, request: Request) -> None:
        now = int(time.time())
        client = request.client.host if request.client else "unknown"
        key = f"ratelimit:{self.name}:{client}:{now // WINDOW_SECONDS}"

        try:
            # incr and expire in one transaction, so every counter gets a TTL
            pipe = redis_conn.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, WINDOW_SECONDS, nx=True)
            count, _ = pipe.execute()
        except RedisError:
            # Fail open: a Redis outage shouldn't block the API.
            log.warning("Redis unavailable, rate limit '%s' not enforced", self.name)
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
