import time
from typing import Any, Dict

class AsyncMemoryCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def get(self, key: str) -> Any:
        if key in self._cache:
            entry = self._cache[key]
            if entry["expires_at"] is None or entry["expires_at"] > time.time():
                return entry["value"]
            else:
                del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._cache[key] = {"value": value, "expires_at": expires_at}

cache = AsyncMemoryCache()
