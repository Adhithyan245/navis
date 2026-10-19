"""
Luma — local meetups, startup/tech events and community gatherings.

Uses Luma's public discovery feed (the one lu.ma's own site calls; not a
documented API, so it's isolated here: cached, paginated gently, and the
base class breaker disables it for 30 min if it starts failing). Events are
tagged tech when their title or host calendar looks tech-related; the rest
are community events.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.event_sources.base import (
    TIMEOUT, EventSource, SourceQuery, blank_event, get_json, in_window, looks_tech,
    tech_subcategory,
)

FEED_URL = "https://api.lu.ma/discover/get-paginated-events"
PAGE_SIZE = 50
MAX_PAGES = 3
CACHE_TTL_S = 15 * 60


def _local(iso: Optional[str], tz: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """UTC ISO → (local YYYY-MM-DD, local HH:MM:SS) in the event's timezone."""
    if not iso:
        return None, None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if tz:
        try:
            dt = dt.astimezone(ZoneInfo(tz))
        except (ZoneInfoNotFoundError, ValueError):
            dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat(), dt.strftime("%H:%M:%S")


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def to_event(entry: Dict[str, Any], q: Optional[SourceQuery] = None) -> Optional[Dict[str, Any]]:
    ev = entry.get("event") or {}
    if not ev.get("api_id") or not ev.get("name"):
        return None
    tz = ev.get("timezone")
    start_date, start_time = _local(ev.get("start_at") or entry.get("start_at"), tz)
    end_date, _ = _local(ev.get("end_at"), tz)
    geo = ev.get("geo_address_info") or {}
    coord = ev.get("coordinate") or {}
    lat, lon = coord.get("latitude"), coord.get("longitude")
    calendar = (entry.get("calendar") or {}).get("name")
    hosts = [h.get("name") for h in entry.get("hosts") or [] if h.get("name")]
    ticket = entry.get("ticket_info") or {}
    online = ev.get("location_type") == "online"
    tech = looks_tech(ev.get("name"), calendar)
    status = "scheduled"
    if ticket.get("is_sold_out"):
        status = "waitlist" if entry.get("waitlist_active") else "soldout"
    distance = None
    if q is not None and lat is not None and lon is not None:
        distance = round(_km(q.lat, q.lon, float(lat), float(lon)), 1)
    price = None
    if ticket.get("price") and isinstance(ticket["price"], dict):
        cents = ticket["price"].get("cents")
        if isinstance(cents, (int, float)):
            price = {"min": cents / 100, "max": None, "currency": (ticket["price"].get("currency") or "USD").upper()}
    return blank_event(
        id=f"luma:{ev['api_id']}",
        source="luma",
        title=ev.get("name"),
        category="tech" if tech else "community",
        subcategory=tech_subcategory(ev.get("name")) if tech else "Community",
        start_date=start_date,
        start_time=start_time,
        start_utc=ev.get("start_at"),
        end_date=end_date,
        timezone=tz,
        status=status,
        online=online,
        venue={
            "name": geo.get("sublocality") or calendar,
            "address": geo.get("full_address") or geo.get("city_state"),
            "city": geo.get("city"),
            "region": geo.get("region"),
            "country": geo.get("country"),
            "country_code": geo.get("country_code"),
            "lat": lat,
            "lon": lon,
        },
        distance_km=distance,
        url=f"https://lu.ma/{ev['url']}" if ev.get("url") else None,
        image=ev.get("cover_url"),
        price=price,
        summary="Free" if ticket.get("is_free") else None,
        locality="online" if online else "city",
        detail={
            "hosts": hosts[:6],
            "calendar": calendar,
            "guest_count": entry.get("guest_count"),
            "requires_approval": bool(ticket.get("require_approval")),
            "free": bool(ticket.get("is_free")),
            "address_hidden": geo.get("mode") == "obfuscated",
        },
    )


class LumaSource(EventSource):
    name = "luma"

    async def fetch(self, q: SourceQuery) -> List[Dict[str, Any]]:
        key = f"events.luma:{q.lat:.2f}:{q.lon:.2f}"
        entries = await cache.get(key)
        if entries is None:
            entries = []
            cursor = None
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                for _ in range(MAX_PAGES):
                    params = {"latitude": f"{q.lat:.4f}", "longitude": f"{q.lon:.4f}",
                              "pagination_limit": PAGE_SIZE}
                    if cursor:
                        params["pagination_cursor"] = cursor
                    data = await get_json(session, FEED_URL, params)
                    entries += data.get("entries") or []
                    cursor = data.get("next_cursor")
                    if not data.get("has_more") or not cursor:
                        break
            await cache.set(key, entries, ttl=CACHE_TTL_S)
        out = []
        for entry in entries:
            event = to_event(entry, q)
            if event and in_window(event["start_date"], event["end_date"], q):
                # Luma's feed is centred on the coordinates but can reach far;
                # keep it to a sensible day-trip radius.
                if event["distance_km"] is not None and event["distance_km"] > 150:
                    continue
                out.append(event)
        return out
