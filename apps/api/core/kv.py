"""
core/kv.py — shared key/value state for caching and rate limits.

With REDIS_URL set, every worker and instance shares one Redis; without it
(local dev, a single instance) everything stays in this process. If Redis
becomes unreachable, calls fall back to process memory instead of failing
requests, and Redis is retried after a short pause.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional, Tuple

import orjson

from apps.api.core.config import settings
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "navis:"
_RETRY_AFTER_S = 30


class _Redis:
    def __init__(self) -> None:
        self._client = None
        self._down_until = 0.0

    def client(self):
        if not settings.REDIS_URL or time.monotonic() < self._down_until:
            return None
        if self._client is None:
            import redis.asyncio as redis  # imported lazily: optional dependency

            try:
                self._client = redis.from_url(
                    settings.REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5, health_check_interval=30
                )
            except ValueError as exc:
                # A malformed REDIS_URL must not take the API down: run on
                # process memory and retry later.
                self.failed(exc)
                return None
        return self._client

    def failed(self, exc: Exception) -> None:
        if time.monotonic() >= self._down_until:
            logger.warning("kv.redis_unavailable", error=type(exc).__name__)
        self._down_until = time.monotonic() + _RETRY_AFTER_S


redis_state = _Redis()


def redis_enabled() -> bool:
    return bool(settings.REDIS_URL)


async def redis_ping() -> Optional[bool]:
    """None when Redis isn't configured; otherwise whether it answers."""
    if not settings.REDIS_URL:
        return None
    client = redis_state.client()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception as exc:  # noqa: BLE001
        redis_state.failed(exc)
        return False


async def redis_get(key: str) -> Tuple[bool, Any]:
    """(found, value). JSON values only."""
    client = redis_state.client()
    if client is None:
        return False, None
    try:
        raw = await client.get(_PREFIX + key)
    except Exception as exc:  # noqa: BLE001
        redis_state.failed(exc)
        return False, None
    if raw is None:
        return False, None
    try:
        return True, orjson.loads(raw)
    except orjson.JSONDecodeError:
        return False, None


async def redis_set(key: str, value: Any, ttl: int) -> None:
    client = redis_state.client()
    if client is None:
        return
    try:
        blob = orjson.dumps(value)
    except TypeError:
        return  # not JSON-serialisable: stays in the local tier only
    try:
        await client.set(_PREFIX + key, blob, ex=max(1, int(ttl)) if ttl else None)
    except Exception as exc:  # noqa: BLE001
        redis_state.failed(exc)


# ── fixed-window counters (rate limits, login throttles) ───────────────────

class _LocalCounters:
    def __init__(self, max_keys: int = 50_000) -> None:
        self._data: "OrderedDict[str, Tuple[int, float]]" = OrderedDict()
        self._max = max_keys

    def incr(self, key: str, window_s: int) -> int:
        now = time.time()
        count, reset = self._data.get(key, (0, now + window_s))
        if reset <= now:
            count, reset = 0, now + window_s
        count += 1
        self._data[key] = (count, reset)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
        return count

    def peek(self, key: str) -> int:
        count, reset = self._data.get(key, (0, 0.0))
        return count if reset > time.time() else 0

    def clear(self, key: str) -> None:
        self._data.pop(key, None)


local_counters = _LocalCounters()


async def incr(key: str, window_s: int) -> int:
    """Increment the counter for this window; returns the new count."""
    client = redis_state.client()
    if client is not None:
        full = f"{_PREFIX}rl:{key}:{int(time.time() // window_s)}"
        try:
            pipe = client.pipeline()
            pipe.incr(full)
            pipe.expire(full, window_s + 1)
            count, _ = await pipe.execute()
            return int(count)
        except Exception as exc:  # noqa: BLE001
            redis_state.failed(exc)
    return local_counters.incr(key, window_s)


async def peek(key: str, window_s: int) -> int:
    client = redis_state.client()
    if client is not None:
        try:
            raw = await client.get(f"{_PREFIX}rl:{key}:{int(time.time() // window_s)}")
            return int(raw or 0)
        except Exception as exc:  # noqa: BLE001
            redis_state.failed(exc)
    return local_counters.peek(key)


async def reset(key: str, window_s: int) -> None:
    client = redis_state.client()
    if client is not None:
        try:
            await client.delete(f"{_PREFIX}rl:{key}:{int(time.time() // window_s)}")
        except Exception as exc:  # noqa: BLE001
            redis_state.failed(exc)
    local_counters.clear(key)


async def allow(key: str, limit: int, window_s: int) -> bool:
    return await incr(key, window_s) <= limit
