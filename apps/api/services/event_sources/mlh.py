"""
MLH (Major League Hacking) — the official collegiate hackathon season.

Parses the public season schedule (robots.txt allows /seasons), which marks
each event up with schema.org Event microdata (url, start/end, attendance
mode, locality/region/country) and the name in the card's first <h4>.
Current and next season are merged.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import aiohttp

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.event_sources.base import (
    TIMEOUT, EventSource, SourceQuery, blank_event, get_text, in_window, place_matches,
)

SEASON_URL = "https://www.mlh.com/seasons/{season}/events"
CACHE_TTL_S = 6 * 60 * 60

_BLOCK = re.compile(r'(?=<a [^>]*itemType="https://schema.org/Event")')
_PROP = re.compile(r'itemProp="(\w+)"(?:\s+content="([^"]*)")?')


def _day(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return iso[:10] if re.match(r"\d{4}-\d{2}-\d{2}", iso) else None


def parse_season(page: str) -> List[Dict[str, Any]]:
    events = []
    for block in _BLOCK.split(page)[1:]:
        props: Dict[str, str] = {}
        for key, value in _PROP.findall(block[:6000]):
            if value and key not in props:
                props[key] = html_lib.unescape(value)
        name_m = re.search(r"<h4[^>]*>([^<]+)</h4>", block)
        href_m = re.search(r'<a [^>]*href="([^"]+)"', block)
        name = html_lib.unescape(name_m.group(1)).strip() if name_m else None
        if not name or not props.get("startDate"):
            continue
        online = "OnlineEventAttendanceMode" in props.get("eventAttendanceMode", "")
        hybrid = "MixedEventAttendanceMode" in props.get("eventAttendanceMode", "")
        events.append({
            "name": name,
            "url": props.get("url") or (html_lib.unescape(href_m.group(1)) if href_m else None),
            "start": props.get("startDate"),
            "end": props.get("endDate"),
            "online": online,
            "hybrid": hybrid,
            "city": props.get("addressLocality"),
            "region": props.get("addressRegion"),
            "country": props.get("addressCountry"),
            "image": props.get("image"),
            "free": props.get("isAccessibleForFree") == "true",
        })
    return events


def to_event(m: Dict[str, Any], locality: Optional[str]) -> Dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{m['name']}-{m['start'][:10]}".lower()).strip("-")
    return blank_event(
        id=f"mlh:{slug}",
        source="mlh",
        title=m["name"],
        category="tech",
        subcategory="hackathon",
        start_date=_day(m["start"]),
        end_date=_day(m.get("end")),
        start_utc=m["start"],
        online=bool(m["online"]),
        hybrid=bool(m["hybrid"]),
        venue={"city": m.get("city"), "region": m.get("region"), "country_code": m.get("country")},
        url=m.get("url"),
        image=m.get("image"),
        summary="Free to attend" if m.get("free") else None,
        locality="online" if m["online"] else locality,
        detail={"league": "MLH", "student_hackathon": True},
    )


class MLHSource(EventSource):
    name = "mlh"

    async def _season_events(self) -> List[Dict[str, Any]]:
        cached = await cache.get("events.mlh.seasons")
        if cached is not None:
            return cached
        today = date.today()
        # MLH seasons are named for the year they end (Aug–Jul).
        seasons = sorted({today.year + (1 if today.month >= 8 else 0), today.year + (2 if today.month >= 8 else 1)})
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            pages = await asyncio.gather(*(get_text(session, SEASON_URL.format(season=s)) for s in seasons),
                                         return_exceptions=True)
        events = [e for p in pages if isinstance(p, str) for e in parse_season(p)]
        if not events and all(isinstance(p, Exception) for p in pages):
            raise pages[0]  # type: ignore[misc]
        await cache.set("events.mlh.seasons", events, ttl=CACHE_TTL_S)
        return events

    async def fetch(self, q: SourceQuery) -> List[Dict[str, Any]]:
        out = []
        for m in await self._season_events():
            if m["online"]:
                locality = "online"
            else:
                locality = place_matches(f"{m.get('city')} {m.get('region')} {m.get('country')}", q)
                if not locality:
                    continue
            e = to_event(m, locality)
            if in_window(e["start_date"], e["end_date"], q):
                out.append(e)
        return out
