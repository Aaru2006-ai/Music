"""
Redis async caching layer.
Handles: metadata cache, rate limiting, session data, pub/sub events.
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from bot.config.config import Config

log = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


# ── Connection ────────────────────────────────────────────────────────────────

async def connect() -> None:
    global _redis
    _redis = await aioredis.from_url(
        Config.REDIS_URI,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        retry_on_timeout=True,
    )
    await _redis.ping()
    log.info("Redis connected successfully.")


async def disconnect() -> None:
    if _redis:
        await _redis.close()
        log.info("Redis disconnected.")


def redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not connected. Call connect() first.")
    return _redis


# ── Generic helpers ───────────────────────────────────────────────────────────

async def set_key(key: str, value: Any, ttl: int = Config.CACHE_TTL) -> None:
    serialised = json.dumps(value) if not isinstance(value, str) else value
    await redis().set(key, serialised, ex=ttl)


async def get_key(key: str) -> Optional[Any]:
    val = await redis().get(key)
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


async def delete_key(key: str) -> None:
    await redis().delete(key)


async def key_exists(key: str) -> bool:
    return bool(await redis().exists(key))


# ── Metadata cache ────────────────────────────────────────────────────────────

TRACK_PREFIX = "track:"

async def cache_track(url: str, data: dict, ttl: int = 3600) -> None:
    await set_key(f"{TRACK_PREFIX}{url}", data, ttl)


async def get_cached_track(url: str) -> Optional[dict]:
    return await get_key(f"{TRACK_PREFIX}{url}")


# ── Rate limiting ─────────────────────────────────────────────────────────────

RATE_PREFIX = "rate:"

async def is_rate_limited(user_id: int, command: str, limit: int = 3, window: int = 10) -> bool:
    """
    Returns True if user has exceeded `limit` calls in `window` seconds.
    """
    key = f"{RATE_PREFIX}{command}:{user_id}"
    pipe = redis().pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    results = await pipe.execute()
    count = results[0]
    return count > limit


# ── Active streams tracker ────────────────────────────────────────────────────

STREAM_PREFIX = "stream:"

async def set_active_stream(chat_id: int, data: dict) -> None:
    await set_key(f"{STREAM_PREFIX}{chat_id}", data, ttl=86400)


async def get_active_stream(chat_id: int) -> Optional[dict]:
    return await get_key(f"{STREAM_PREFIX}{chat_id}")


async def delete_active_stream(chat_id: int) -> None:
    await delete_key(f"{STREAM_PREFIX}{chat_id}")


async def get_all_active_streams() -> list:
    keys = await redis().keys(f"{STREAM_PREFIX}*")
    streams = []
    for key in keys:
        data = await get_key(key)
        if data:
            streams.append(data)
    return streams


# ── Volume / Settings cache ───────────────────────────────────────────────────

async def set_volume(chat_id: int, volume: int) -> None:
    await set_key(f"vol:{chat_id}", volume, ttl=86400)


async def get_volume(chat_id: int) -> int:
    val = await get_key(f"vol:{chat_id}")
    return int(val) if val is not None else 100


# ── Blacklist cache ───────────────────────────────────────────────────────────

BANNED_KEY = "banned_users"

async def add_to_ban_cache(user_id: int) -> None:
    await redis().sadd(BANNED_KEY, str(user_id))


async def remove_from_ban_cache(user_id: int) -> None:
    await redis().srem(BANNED_KEY, str(user_id))


async def is_in_ban_cache(user_id: int) -> bool:
    return await redis().sismember(BANNED_KEY, str(user_id))


async def load_ban_cache(user_ids: list) -> None:
    if user_ids:
        await redis().sadd(BANNED_KEY, *[str(uid) for uid in user_ids])


# ── Pause state ───────────────────────────────────────────────────────────────

async def set_paused(chat_id: int, paused: bool) -> None:
    await set_key(f"paused:{chat_id}", paused, ttl=86400)


async def is_paused(chat_id: int) -> bool:
    val = await get_key(f"paused:{chat_id}")
    return bool(val)


# ── Loop / Shuffle state ──────────────────────────────────────────────────────

async def set_loop(chat_id: int, active: bool) -> None:
    await set_key(f"loop:{chat_id}", active, ttl=86400)


async def get_loop(chat_id: int) -> bool:
    return bool(await get_key(f"loop:{chat_id}"))


async def set_shuffle(chat_id: int, active: bool) -> None:
    await set_key(f"shuffle:{chat_id}", active, ttl=86400)


async def get_shuffle(chat_id: int) -> bool:
    return bool(await get_key(f"shuffle:{chat_id}"))
  
