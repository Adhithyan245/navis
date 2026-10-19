"""
Live safety alerts near a place, from free public feeds:

  * U.S. National Weather Service (api.weather.gov): active watches and
    warnings for the exact point (US only)
  * GDACS (UN / EU Global Disaster Alert and Coordination System): orange
    and red alerts for cyclones, floods, earthquakes, volcanoes, wildfires
    and droughts within ~600 km, anywhere in the world
  * USGS: earthquakes of magnitude 4.5+ within 300 km in the last 7 days
    (worldwide weekly summary feed, filtered locally)

Each source is optional: a failing feed is skipped, never fatal.
Returns [{kind, title, detail, severity, starts, ends, source, url}],
most severe first.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import PlaceRef, distance_m, get_json

_UA = {"User-Agent": "Navis/1.0 (city companion; https://navis.app)", "Accept": "application/geo+json"}
_GDACS_KINDS = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano",
                "WF": "Wildfire", "DR": "Drought"}
_SEVERITY_RANK = {"extreme": 0, "red": 0, "severe": 1, "orange": 1, "moderate": 2, "minor": 3, "unknown": 4}


async def _nws(place: PlaceRef) -> List[Dict[str, Any]]:
    if place.country_code and place.country_code.upper() != "US":
        return []
    data = await get_json("https://api.weather.gov/alerts/active",
                          params={"point": f"{place.lat:.4f},{place.lon:.4f}"}, headers=_UA)
    out = []
    for feat in (data or {}).get("features") or []:
        p = feat.get("properties") or {}
        if p.get("status") not in (None, "Actual"):
            continue
        out.append({
            "kind": "weather",
            "title": p.get("event") or "Weather alert",
            "detail": (p.get("headline") or "")[:280],
            "instruction": (p.get("instruction") or "")[:400] or None,
            "severity": (p.get("severity") or "unknown").lower(),
            "starts": p.get("onset") or p.get("effective"),
            "ends": p.get("ends") or p.get("expires"),
            "source": "U.S. National Weather Service",
            "url": "https://www.weather.gov/",
        })
    return out


async def _gdacs(place: PlaceRef) -> List[Dict[str, Any]]:
    data = await cache.get("alerts.gdacs")
    if data is None:
        data = await get_json("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
                              params={"alertlevel": "Orange;Red", "eventlist": "EQ;TC;FL;VO;WF;DR"})
        if data is None:
            return []
        await cache.set("alerts.gdacs", data, ttl=15 * 60)
    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    out = []
    for feat in data.get("features") or []:
        p = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
            to = datetime.fromisoformat(str(p.get("todate"))).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if to < cutoff or distance_m(place.lat, place.lon, lat, lon) > 600_000:
            continue
        sev = (p.get("severitydata") or {}).get("severitytext")
        out.append({
            "kind": "disaster",
            "title": p.get("name") or _GDACS_KINDS.get(p.get("eventtype"), "Disaster alert"),
            "detail": sev or f"{_GDACS_KINDS.get(p.get('eventtype'), 'Event')} affecting {p.get('country') or 'the region'}",
            "instruction": None,
            "severity": str(p.get("alertlevel") or "unknown").lower(),
            "starts": p.get("fromdate"),
            "ends": p.get("todate"),
            "distance_km": round(distance_m(place.lat, place.lon, lat, lon) / 1000),
            "source": "GDACS",
            "url": (p.get("url") or {}).get("report"),
        })
    return out


async def _quakes(place: PlaceRef) -> List[Dict[str, Any]]:
    # The USGS summary feed (M4.5+, past 7 days, worldwide) is small and fast;
    # one cached copy serves every place.
    data = await cache.get("alerts.usgs_week")
    if data is None:
        data = await get_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson")
        if data is None:
            return []
        await cache.set("alerts.usgs_week", data, ttl=10 * 60)
    out = []
    for feat in data.get("features") or []:
        p = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        km = distance_m(place.lat, place.lon, float(coords[1]), float(coords[0])) / 1000
        if km > 300:
            continue
        mag = p.get("mag")
        when = p.get("time")
        out.append({
            "kind": "earthquake",
            "title": f"M{mag:.1f} earthquake" if isinstance(mag, (int, float)) else "Earthquake",
            "detail": p.get("place") or "",
            "instruction": None,
            "severity": "severe" if isinstance(mag, (int, float)) and mag >= 6 else "moderate",
            "starts": datetime.fromtimestamp(when / 1000, timezone.utc).isoformat() if isinstance(when, (int, float)) else None,
            "ends": None,
            "distance_km": round(km),
            "source": "USGS",
            "url": p.get("url"),
        })
    out.sort(key=lambda a: a["distance_km"])
    return out[:5]


async def alerts_near(place: PlaceRef) -> Optional[List[Dict[str, Any]]]:
    """Active alerts near the place; None only if every feed failed."""
    key = f"alerts.near:{place.lat:.2f}:{place.lon:.2f}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    found = await asyncio.gather(_nws(place), _gdacs(place), _quakes(place), return_exceptions=True)
    ok = [f for f in found if isinstance(f, list)]
    if not ok:
        return None
    items = [a for group in ok for a in group]
    items.sort(key=lambda a: _SEVERITY_RANK.get(a["severity"], 4))
    items = items[:8]
    await cache.set(key, items, ttl=10 * 60)
    return items
