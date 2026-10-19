"""
Shared pieces for the domain data services (weather, money, safety, transit,
arrival, local knowledge).

Every service returns the same result shape, which the agent layer passes
through as an AgentResult:

    {status: "ok"|"partial"|"empty"|"unavailable", data: {...},
     message: str, alternatives: [str], sources: [str]}

`message` is user-facing: friendly, positive and free of provider names.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

import aiohttp

from apps.api.core.config import settings
from apps.api.core.http import get_session
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache

logger = get_logger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=10)


@dataclass(frozen=True)
class PlaceRef:
    lat: float
    lon: float
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None

    @property
    def label(self) -> str:
        return self.city or self.country or "this area"


def result(status: str, data: Optional[Dict[str, Any]] = None, *, message: str = "",
           alternatives: Sequence[str] = (), sources: Sequence[str] = ()) -> Dict[str, Any]:
    return {"status": status, "data": data or {}, "message": message,
            "alternatives": list(alternatives), "sources": list(sources)}


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


async def nearby(place: PlaceRef, categories: str, *, radius_m: int = 5000, limit: int = 20) -> Optional[List[Dict[str, Any]]]:
    """Places of the given Geoapify categories near the place, nearest first.
    None when the lookup itself failed (vs [] for 'nothing there')."""
    key = settings.GEOAPIFY_API_KEY
    if not key:
        return None
    ck = f"domain.nearby:{categories}:{place.lat:.3f}:{place.lon:.3f}:{radius_m}:{limit}"
    cached = await cache.get(ck)
    if cached is not None:
        return cached
    url = (
        "https://api.geoapify.com/v2/places"
        f"?categories={quote(categories, safe=',.')}"
        f"&filter=circle:{place.lon},{place.lat},{int(radius_m)}"
        f"&bias=proximity:{place.lon},{place.lat}"
        f"&limit={max(1, min(limit, 100))}&apiKey={key}"
    )
    try:
        async with get_session().get(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning("domain.nearby.bad_status", status=resp.status, categories=categories)
                return None
            data = await resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("domain.nearby.error", error=type(exc).__name__, categories=categories)
        return None
    out = []
    for feat in data.get("features") or []:
        p = feat.get("properties") or {}
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        cats = p.get("categories") or []
        raw = (p.get("datasource") or {}).get("raw") or {}
        out.append({
            "tags": {k: raw[k] for k in ("iata", "aerodrome:type", "aerodrome", "operator", "network")
                     if k in raw},
            "name": p.get("name") or p.get("address_line1") or "Unnamed",
            "address": p.get("address_line2") or p.get("formatted"),
            "categories": cats,
            "lat": lat,
            "lon": lon,
            "distance_m": round(distance_m(place.lat, place.lon, lat, lon)),
            "phone": (p.get("contact") or {}).get("phone") or (p.get("datasource", {}).get("raw") or {}).get("phone"),
            "website": p.get("website") or (p.get("datasource", {}).get("raw") or {}).get("website"),
            "opening_hours": p.get("opening_hours") or (p.get("datasource", {}).get("raw") or {}).get("opening_hours"),
        })
    out.sort(key=lambda x: x["distance_m"])
    await cache.set(ck, out, ttl=6 * 3600)
    return out


async def get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Optional[Any]:
    try:
        async with get_session().get(url, params=params, timeout=TIMEOUT,
                                     headers=headers or {"User-Agent": "Navis/1.0"}) as resp:
            if resp.status != 200:
                logger.warning("domain.http.bad_status", url=url.split("?")[0], status=resp.status)
                return None
            return await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("domain.http.error", url=url.split("?")[0], error=type(exc).__name__)
        return None
