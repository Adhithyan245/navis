"""
Bike share near a place (CityBikes, api.citybik.es: ~800 systems worldwide,
free, no key). Returns the nearest network with live free-bike / empty-dock
counts at its closest stations, or None.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import PlaceRef, distance_m, get_json

_BASE = "https://api.citybik.es/v2/networks"
_MAX_NETWORK_KM = 25


async def _networks() -> Optional[list]:
    cached = await cache.get("bikeshare.networks")
    if cached is not None:
        return cached
    data = await get_json(_BASE, params={"fields": "id,name,location,company,href"})
    nets = (data or {}).get("networks")
    if nets:
        await cache.set("bikeshare.networks", nets, ttl=24 * 3600)
    return nets


async def bikeshare_near(place: PlaceRef, *, stations: int = 5) -> Optional[Dict[str, Any]]:
    nets = await _networks()
    if not nets:
        return None
    best, best_d = None, None
    for n in nets:
        loc = n.get("location") or {}
        try:
            d = distance_m(place.lat, place.lon, float(loc["latitude"]), float(loc["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        if best_d is None or d < best_d:
            best, best_d = n, d
    if not best or best_d is None or best_d > _MAX_NETWORK_KM * 1000:
        return None
    key = f"bikeshare.stations:{best['id']}"
    detail = await cache.get(key)
    if detail is None:
        detail = await get_json(f"{_BASE}/{best['id']}", params={"fields": "stations,name,company"})
        if not detail:
            return None
        await cache.set(key, detail, ttl=120)  # live counts
    rows = []
    for s in ((detail.get("network") or {}).get("stations") or []):
        try:
            d = distance_m(place.lat, place.lon, float(s["latitude"]), float(s["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"name": s.get("name"), "lat": s["latitude"], "lon": s["longitude"],
                     "free_bikes": s.get("free_bikes"), "empty_slots": s.get("empty_slots"),
                     "distance_m": round(d)})
    rows.sort(key=lambda r: r["distance_m"])
    company = best.get("company")
    return {
        "network": best.get("name"),
        "operator": ", ".join(company) if isinstance(company, list) else company,
        "city": (best.get("location") or {}).get("city"),
        "stations": rows[:stations],
    }
