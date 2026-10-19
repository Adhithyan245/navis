"""
The app-wide cache: a bounded in-process LRU (always), plus Redis shared
across workers/instances when REDIS_URL is set. Values must be
JSON-serialisable to reach Redis; anything else stays process-local.
"""
import asyncio
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable

from apps.api.core import kv
from apps.api.core.config import settings


class AsyncMemoryCache:
    def __init__(self, max_entries: int = 5000):
        self._cache: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = asyncio.Lock()
        self._max = max_entries

    async def _local_get(self, key: str) -> Any:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry["expires_at"] is not None and entry["expires_at"] <= time.time():
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return entry["value"]

    async def _local_set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            self._cache[key] = {"value": value, "expires_at": time.time() + ttl if ttl else None}
            self._cache.move_to_end(key)
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)

    async def get(self, key: str) -> Any:
        value = await self._local_get(key)
        if value is not None:
            return value
        found, value = await kv.redis_get("c:" + key)
        if found and value is not None:
            # Short local copy so hot keys don't hit Redis on every request.
            await self._local_set(key, value, 60)
            return value
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        await self._local_set(key, value, ttl)
        await kv.redis_set("c:" + key, value, ttl)


cache = AsyncMemoryCache(settings.CACHE_MAX_ENTRIES)


def ttl_cache(ttl: int = 3600):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            cached_result = await cache.get(key)
            if cached_result is not None:
                return cached_result
            result = await func(*args, **kwargs)
            await cache.set(key, result, ttl=ttl)
            return result
        return wrapper
    return decorator
