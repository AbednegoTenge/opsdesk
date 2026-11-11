"""Refresh-token state in Redis.

Each issued refresh token is recorded under its `jti` with a TTL equal to the token's
remaining lifetime. A refresh token is accepted only while its key exists, so:

* rotation  = atomically consume the old key (GETDEL) and record the new token;
* logout    = delete the key;
* revoke all for a user (password change, deactivation, role change)
            = delete every key in the user's index set.

All API replicas share this state through Redis; nothing is kept in process memory.
"""

import logging
import time

import redis
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import ServiceUnavailable
from apps.core.redis_client import get_redis

logger = logging.getLogger(__name__)


def _token_key(jti: str) -> str:
    return f"{settings.REFRESH_TOKEN_KEY_PREFIX}:jti:{jti}"


def _user_key(user_id) -> str:
    return f"{settings.REFRESH_TOKEN_KEY_PREFIX}:user:{user_id}"


def _ttl_seconds(token: RefreshToken) -> int:
    return max(1, int(token["exp"] - time.time()))


def _redis_call(fn):
    try:
        return fn(get_redis())
    except redis.RedisError as exc:
        logger.error("refresh token store unavailable", extra={"error": str(exc)})
        raise ServiceUnavailable() from exc


def record(token: RefreshToken) -> None:
    """Remember a newly issued refresh token."""
    jti, user_id, ttl = token["jti"], token["user_id"], _ttl_seconds(token)
    max_ttl = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())

    def _do(r):
        pipe = r.pipeline(transaction=True)
        pipe.set(_token_key(jti), str(user_id), ex=ttl)
        pipe.sadd(_user_key(user_id), jti)
        pipe.expire(_user_key(user_id), max_ttl)
        pipe.execute()

    _redis_call(_do)


def consume(token: RefreshToken) -> bool:
    """Atomically use a refresh token once. False if it was revoked or already used."""
    jti, user_id = token["jti"], token["user_id"]

    def _do(r):
        stored = r.getdel(_token_key(jti))
        r.srem(_user_key(user_id), jti)
        return stored is not None and stored == str(user_id)

    return _redis_call(_do)


def revoke(token: RefreshToken) -> None:
    jti, user_id = token["jti"], token["user_id"]

    def _do(r):
        pipe = r.pipeline(transaction=True)
        pipe.delete(_token_key(jti))
        pipe.srem(_user_key(user_id), jti)
        pipe.execute()

    _redis_call(_do)


def revoke_all(user_id) -> int:
    """Revoke every refresh token of a user. Returns how many were revoked."""

    def _do(r):
        jtis = r.smembers(_user_key(user_id))
        pipe = r.pipeline(transaction=True)
        for jti in jtis:
            pipe.delete(_token_key(jti))
        pipe.delete(_user_key(user_id))
        pipe.execute()
        return len(jtis)

    count = _redis_call(_do)
    logger.info("revoked refresh tokens", extra={"user_id": user_id, "count": count})
    return count


def issue_for(user) -> RefreshToken:
    """Create a refresh token (and its access token) for a user and record it."""
    token = RefreshToken.for_user(user)
    token["role"] = user.role
    record(token)
    return token
