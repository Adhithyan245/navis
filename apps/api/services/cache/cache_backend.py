"""
services/cache/cache_backend.py

Abstract cache interface that supports two backends:
  - MemoryBackend  (single-instance, zero-dependency, default)
  - RedisBackend   (multi-instance ready, stub — activate when Redis is available)

Swap the backend via settings.CACHE_BACKEND = "memory" | "redis"
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Optional


# ── Abstract interface ─────────────────────────────────────────────────────────

class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 300) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...


# ── Memory backend (production default) ────────────────────────────────────────

class MemoryBackend(CacheBackend):
    def __init__(self):
        self._store: dict = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry["exp"] and entry["exp"] < time.monotonic():
                del self._store[key]
                return None
            return entry["value"]

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        async with self._lock:
            exp = time.monotonic() + ttl if ttl else None
            self._store[key] = {"value": value, "exp": exp}

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()


# ── Redis backend stub (activate when Redis is provisioned) ────────────────────

class RedisBackend(CacheBackend):
    """
    Stub implementation. Replace body with aioredis calls when Redis
    is available in the deployment environment.
    """
    def __init__(self, url: str = "redis://localhost:6379"):
        self.url = url
        self._client = None  # aioredis.from_url(url)

    async def get(self, key: str) -> Optional[Any]:
        # value = await self._client.get(key)
        # return pickle.loads(value) if value else None
        raise NotImplementedError("Redis backend not yet activated")

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        # await self._client.set(key, pickle.dumps(value), ex=ttl)
        raise NotImplementedError("Redis backend not yet activated")

    async def delete(self, key: str) -> None:
        # await self._client.delete(key)
        raise NotImplementedError("Redis backend not yet activated")

    async def clear(self) -> None:
        # await self._client.flushdb()
        raise NotImplementedError("Redis backend not yet activated")


# ── Singleton cache instance ───────────────────────────────────────────────────

cache_backend: CacheBackend = MemoryBackend()
