"""
Shared plumbing for event source adapters.

Each adapter implements `EventSource.fetch(query) -> list[event]` returning
events in EventsService's schema (see services/events_service.py
`_tm_event`). Adapters are fail-soft: `safe_fetch` turns any failure into
[] and trips a per-source breaker (3 consecutive failures → skip for 30
min) so a broken or blocked source never slows the page.
"""
from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import aiohttp

from apps.api.core.logging import get_logger

logger = get_logger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; NavisBot/1.0; +https://navis.app)"
TIMEOUT = aiohttp.ClientTimeout(total=12)

_FAILS_TO_OPEN = 3
_OPEN_FOR_S = 30 * 60


@dataclass(frozen=True)
class SourceQuery:
    lat: float
    lon: float
    city: Optional[str]
    region: Optional[str]
    country: Optional[str]
    country_code: Optional[str]
    start: date
    end: date
    keyword: Optional[str] = None


class EventSource(ABC):
    name: str = "source"

    def __init__(self) -> None:
        self._fails = 0
        self._open_until = 0.0

    @abstractmethod
    async def fetch(self, q: SourceQuery) -> List[Dict[str, Any]]:
        ...

    async def safe_fetch(self, q: SourceQuery) -> List[Dict[str, Any]]:
        if time.time() < self._open_until:
            return []
        try:
            events = await self.fetch(q)
        except Exception as exc:  # noqa: BLE001
            self._fails += 1
            if self._fails >= _FAILS_TO_OPEN:
                self._open_until = time.time() + _OPEN_FOR_S
                self._fails = 0
            logger.warning("events.source_failed", source=self.name, error=str(exc))
            return []
        self._fails = 0
        return events


async def get_json(session: aiohttp.ClientSession, url: str, params: Optional[dict] = None) -> Any:
    async with session.get(url, params=params, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as r:
        r.raise_for_status()
        return await r.json(content_type=None)


async def get_text(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        return await r.text()


# ── helpers ────────────────────────────────────────────────────────────────

def norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).strip()


_TECH_WORDS = (
    "ai", "a i", "ml", "llm", "genai", "gpt", "startup", "founder", "founders", "vc", "venture",
    "developer", "developers", "dev", "devs", "engineering", "engineer", "code", "coding",
    "hackathon", "hack", "data", "cloud", "aws", "gcp", "azure", "kubernetes", "python",
    "javascript", "react", "web3", "crypto", "blockchain", "product", "design", "ux", "saas",
    "tech", "robotics", "biotech", "medtech", "fintech", "cleantech", "climate tech", "cyber",
    "security", "open source", "machine learning", "deep learning", "pitch", "demo day",
    "innovation", "builders", "agents", "devops", "api",
)


def looks_tech(*texts: Any) -> bool:
    blob = f" {' '.join(norm(t) for t in texts)} "
    return any(f" {w} " in blob for w in _TECH_WORDS)


def tech_subcategory(*texts: Any) -> str:
    blob = " ".join(norm(t) for t in texts)
    if "hackathon" in blob or re.search(r"\bhack\b", blob):
        return "hackathon"
    if "workshop" in blob or "bootcamp" in blob or "masterclass" in blob:
        return "workshop"
    if "conference" in blob or "summit" in blob or "expo" in blob or "fest" in blob:
        return "conference"
    return "meetup"


def place_matches(location_text: Any, q: SourceQuery) -> Optional[str]:
    """'city' | 'country' | None for a free-text location vs the query place."""
    loc = f" {norm(location_text)} "
    if q.city and f" {norm(q.city)} " in loc:
        return "city"
    if q.region and len(q.region) > 2 and f" {norm(q.region)} " in loc:
        return "country"
    names = {norm(q.country)} if q.country else set()
    if q.country_code:
        names.add(norm(q.country_code))
        if q.country_code.upper() == "US":
            names |= {"usa", "united states", "us"}
        if q.country_code.upper() == "GB":
            names |= {"uk", "united kingdom", "england"}
    if any(n and f" {n} " in loc for n in names):
        return "country"
    return None


def blank_event(**fields: Any) -> Dict[str, Any]:
    """An event dict with every schema key present."""
    venue = {"name": None, "address": None, "city": None, "region": None, "country": None,
             "country_code": None, "postcode": None, "lat": None, "lon": None}
    venue.update(fields.pop("venue", {}) or {})
    event = {
        "id": None, "source": None, "title": None, "category": "tech", "subcategory": None,
        "start_date": None, "start_time": None, "start_utc": None, "end_date": None,
        "timezone": None, "status": "scheduled", "online": False, "hybrid": False,
        "venue": venue, "distance_km": None, "url": None, "image": None, "price": None,
        "summary": None, "locality": None, "detail": {},
    }
    event.update(fields)
    return event


def in_window(start: Optional[str], end: Optional[str], q: SourceQuery) -> bool:
    if not start:
        return False
    end = end or start
    return not (end < q.start.isoformat() or start > q.end.isoformat())
