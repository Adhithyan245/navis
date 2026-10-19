"""
dev.events — developer conferences, masterclasses and community days
worldwide, from the public RSS feed. Each item's description reads
"<Name> is happening on <Month D, YYYY>[ in City, Country, Continent | , Online]".
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from apps.api.services.cache.ttl_cache import cache
from apps.api.services.event_sources.base import (
    TIMEOUT, EventSource, SourceQuery, blank_event, get_text, in_window, place_matches,
    tech_subcategory,
)

RSS_URL = "https://dev.events/rss.xml"
CACHE_TTL_S = 3 * 60 * 60

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_HAPPENING = re.compile(r"is happening on ([A-Z][a-z]+ \d{1,2}, \d{4})(?:,\s*(Online)|\s+in\s+([^.]+?))\.\s", re.S)


def _tag(item: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", item, re.S)
    return html_lib.unescape(m.group(1).strip()) if m else None


def parse_rss(xml: str) -> List[Dict[str, Any]]:
    out = []
    for item in _ITEM.findall(xml):
        title, link = _tag(item, "title"), _tag(item, "link")
        desc = (_tag(item, "description") or "") + " "
        m = _HAPPENING.search(desc)
        if not title or not link or not m:
            continue
        try:
            day = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
        except ValueError:
            continue
        location = (m.group(3) or "").strip()
        parts = [p.strip() for p in location.split(",")] if location else []
        out.append({
            "title": title,
            "url": link,
            "date": day,
            "online": bool(m.group(2)),
            "location": location,
            "city": parts[0] if parts else None,
            "country": parts[1] if len(parts) > 1 else None,
            "topics": re.findall(r"<category>(.*?)</category>", item)[:4],
            "guid": _tag(item, "guid") or link,
        })
    return out


class DevEventsSource(EventSource):
    name = "devevents"

    async def fetch(self, q: SourceQuery) -> List[Dict[str, Any]]:
        items = await cache.get("events.devevents.rss")
        if items is None:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                items = parse_rss(await get_text(session, RSS_URL))
            await cache.set("events.devevents.rss", items, ttl=CACHE_TTL_S)
        out = []
        for it in items:
            locality = "online" if it["online"] else place_matches(it["location"], q)
            if not locality or not in_window(it["date"], it["date"], q):
                continue
            out.append(blank_event(
                id=f"devev:{it['guid']}",
                source="devevents",
                title=it["title"],
                subcategory=tech_subcategory(it["title"], " ".join(it["topics"])),
                start_date=it["date"],
                end_date=it["date"],
                online=it["online"],
                venue={"city": it["city"], "country": it["country"]},
                url=it["url"],
                locality=locality,
                detail={"topics": it["topics"]},
            ))
        return out
