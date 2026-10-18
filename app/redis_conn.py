"""The shared Redis connection: rate limiting now; caching and click events later."""

import os

from redis import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# from_url doesn't connect yet; it opens pooled connections on first use.
# Short timeouts: if Redis is slow or down, callers find out quickly and can fall back,
# instead of every request hanging.
redis_client = Redis.from_url(
    REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True
)
