"""
Provider-level response cache.

Caches only raw provider responses — never fabricated derivatives.
Cache keys include city + query/category to avoid cross-contamination.
User-specific DB data is NEVER cached here.

TTL Policy Table:
  google_places  — 300s  (5 min)  — place data changes infrequently
  eventbrite     — 180s  (3 min)  — events update moderately
  osm_overpass   — 600s  (10 min) — infrastructure rarely changes
  mbta_routes    — 120s  (2 min)  — alerts/routes can change quickly
"""

import time
from typing import Any, Dict, Optional

# Per-provider TTL in seconds
TTL_TABLE: Dict[str, int] = {
    "google_places": 300,
    "eventbrite": 180,
    "osm_overpass": 600,
    "mbta": 120,
    "yelp": 300,          # Same cadence as Google Places
    "ticketmaster": 180,  # Same cadence as Eventbrite
    "adzuna": 600,        # Job listings change slowly
}

_cache: Dict[str, Dict[str, Any]] = {}


def _make_key(provider: str, city: str, query: str = "") -> str:
    return f"{provider}:{city.lower().strip()}:{query.lower().strip()}"


def cache_get(provider: str, city: str, query: str = "") -> Optional[Dict[str, Any]]:
    """Retrieve a cached provider response if TTL has not expired."""
    key = _make_key(provider, city, query)
    entry = _cache.get(key)
    if entry is None:
        return None
    ttl = TTL_TABLE.get(provider, 120)
    if time.time() - entry["ts"] > ttl:
        del _cache[key]
        return None
    return entry["data"]


def cache_set(provider: str, city: str, query: str, data: Dict[str, Any]) -> None:
    """Store a provider response in cache with timestamp."""
    key = _make_key(provider, city, query)
    _cache[key] = {"data": data, "ts": time.time()}


def cache_invalidate(provider: str, city: str = "", query: str = "") -> int:
    """Invalidate cache entries. Returns number of entries removed."""
    if city and query:
        key = _make_key(provider, city, query)
        return 1 if _cache.pop(key, None) else 0

    prefix = f"{provider}:"
    if city:
        prefix = f"{provider}:{city.lower().strip()}:"
    keys_to_remove = [k for k in _cache if k.startswith(prefix)]
    for k in keys_to_remove:
        del _cache[k]
    return len(keys_to_remove)


def cache_stats() -> Dict[str, Any]:
    """Return current cache size and per-provider entry counts."""
    counts: Dict[str, int] = {}
    now = time.time()
    live = 0
    expired = 0
    for key, entry in list(_cache.items()):
        provider = key.split(":")[0]
        ttl = TTL_TABLE.get(provider, 120)
        if now - entry["ts"] > ttl:
            expired += 1
        else:
            live += 1
            counts[provider] = counts.get(provider, 0) + 1
    return {"total_live": live, "total_expired": expired, "per_provider": counts}
