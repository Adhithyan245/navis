"""
Devpost — hackathons, in person and online.

Uses Devpost's public JSON listing (/api/hackathons). In-person hackathons
are matched to the place by their location text; online ones are offered
to everyone.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.event_sources.base import (
    TIMEOUT, EventSource, SourceQuery, blank_event, get_json, in_window, place_matches,
)

LIST_URL = "https://devpost.com/api/hackathons"
IN_PERSON_PAGES = 12   # 9 per page; ~100 upcoming in-person hackathons
ONLINE_PAGES = 3
CACHE_TTL_S = 60 * 60

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_period(text: str, today: Optional[date] = None) -> Tuple[Optional[str], Optional[str]]:
    """'Oct 30 - Dec 04, 2026' / 'Oct 01 - 30, 2026' / 'Dec 28, 2026 - Jan 03, 2027'."""
    today = today or date.today()
    t = (text or "").replace("–", "-").strip()
    m = re.match(r"([A-Za-z]{3})\s+(\d{1,2})(?:,\s*(\d{4}))?\s*-\s*(?:([A-Za-z]{3})\s+)?(\d{1,2}),\s*(\d{4})", t)
    if not m:
        return None, None
    m1, d1, y1, m2, d2, y2 = m.groups()
    try:
        end = date(int(y2), _MONTHS[(m2 or m1).lower()], int(d2))
        start = date(int(y1) if y1 else int(y2), _MONTHS[m1.lower()], int(d1))
        if start > end:  # spans New Year without an explicit start year
            start = date(start.year - 1, start.month, start.day)
    except (KeyError, ValueError):
        return None, None
    return start.isoformat(), end.isoformat()


def _prize(raw: Any) -> Optional[str]:
    text = re.sub(r"<[^>]+>", "", str(raw or "")).strip()
    return text if re.search(r"\d", text) else None


def to_event(h: Dict[str, Any], locality: Optional[str]) -> Optional[Dict[str, Any]]:
    start, end = parse_period(h.get("submission_period_dates") or "")
    if not h.get("id") or not h.get("title") or not start:
        return None
    loc = h.get("displayed_location") or {}
    online = loc.get("icon") == "globe" or str(loc.get("location", "")).lower() == "online"
    thumb = h.get("thumbnail_url")
    themes = [t.get("name") for t in h.get("themes") or [] if t.get("name")]
    return blank_event(
        id=f"devpost:{h['id']}",
        source="devpost",
        title=h["title"],
        category="tech",
        subcategory="hackathon",
        start_date=start,
        end_date=end,
        status="scheduled" if h.get("open_state") in ("open", "upcoming") else h.get("open_state"),
        online=online,
        venue={"name": None if online else loc.get("location")},
        url=h.get("url"),
        image=f"https:{thumb}" if isinstance(thumb, str) and thumb.startswith("//") else thumb,
        summary=f"Prizes: {_prize(h.get('prize_amount'))}" if _prize(h.get("prize_amount")) else None,
        locality="online" if online else locality,
        detail={
            "organizer": h.get("organization_name"),
            "themes": themes[:6],
            "registrations": h.get("registrations_count"),
            "prizes": _prize(h.get("prize_amount")),
            "submission_period": h.get("submission_period_dates"),
            "time_left": h.get("time_left_to_submission"),
            "invite_only": bool(h.get("invite_only")),
        },
    )


class DevpostSource(EventSource):
    name = "devpost"

    async def _listing(self, challenge_type: str, pages: int) -> List[Dict[str, Any]]:
        key = f"events.devpost:{challenge_type}"
        cached = await cache.get(key)
        if cached is not None:
            return cached
        sem = asyncio.Semaphore(3)
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async def page(n: int):
                async with sem:
                    data = await get_json(session, LIST_URL, {
                        "status[]": ["upcoming", "open"], "challenge_type[]": challenge_type, "page": n})
                    return data.get("hackathons") or []
            results = await asyncio.gather(*(page(n) for n in range(1, pages + 1)), return_exceptions=True)
        rows = [h for r in results if isinstance(r, list) for h in r]
        if not rows and any(isinstance(r, Exception) for r in results):
            raise next(r for r in results if isinstance(r, Exception))
        await cache.set(key, rows, ttl=CACHE_TTL_S)
        return rows

    async def fetch(self, q: SourceQuery) -> List[Dict[str, Any]]:
        in_person, online = await asyncio.gather(
            self._listing("in-person", IN_PERSON_PAGES), self._listing("online", ONLINE_PAGES))
        out: List[Dict[str, Any]] = []
        for h in in_person:
            locality = place_matches((h.get("displayed_location") or {}).get("location"), q)
            if not locality:
                continue
            e = to_event(h, locality)
            if e and in_window(e["start_date"], e["end_date"], q):
                out.append(e)
        for h in online:
            e = to_event(h, "online")
            if e and in_window(e["start_date"], e["end_date"], q):
                out.append(e)
        return out
