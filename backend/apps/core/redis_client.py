"""Single place that builds the Redis client so tests can swap it."""

from functools import lru_cache

import redis
from django.conf import settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(
        settings.REDIS_URL,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
        health_check_interval=30,
        decode_responses=True,
    )
