import os

from redis import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# short timeouts so a slow or dead Redis can't hang requests
redis_client = Redis.from_url(
    REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True
)
