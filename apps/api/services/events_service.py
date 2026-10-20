"""
EventsService — what's on near a place, from several sources, in one shape.

Sources (each optional, each fail-soft):
  * Ticketmaster Discovery — concerts, sports, arts & theatre, family, film,
    with exact times, venue, prices and ticket links. Strong in North
    America, Europe and Oceania; sparse or empty elsewhere.
  * confs.tech open dataset — tech conferences worldwide (32 topics),
    including online events.
  * Nager.Date — public holidays and observances for ~100 countries (useful
    for newcomers: festivals, and days when shops and offices close).

No free API lists every local event on Earth, so when an area is sparse the
radius widens automatically and the response says how far it searched.
Nothing is invented: every event comes from a source and links back to it.

Event dicts share one schema (see `_tm_event`); detail lookups add the
source's long-form fields (`detail`).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache
from apps.api.services.event_sources import TECH_SOURCES, SourceQuery
from apps.api.services.event_sources.base import norm as _norm_title

logger = get_logger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=12)

CATEGORIES = ("music", "sports", "arts", "comedy", "family", "film", "tech", "community", "holiday")

# Ticketmaster classificationName per category (None = not a TM category).
_TM_CLASS = {
    "music": "music", "sports": "sports", "arts": "arts & theatre",
    "comedy": "comedy", "family": "family", "film": "film",
    "community": "miscellaneous",
}
_TM_RADII_KM = (25, 100, 300)
_ONLINE_IN_MIXED = 6
_TM_ENOUGH = 8

_CONF_TOPICS = (
    "accessibility", "android", "api", "clojure", "cpp", "css", "data", "devops",
    "dotnet", "general", "graphql", "groovy", "haskell", "ios", "iot", "java",
    "javascript", "kotlin", "leadership", "networking", "opensource",
    "performance", "php", "product", "python", "rust", "security", "sre",
    "tech-comm", "testing", "typescript", "ux",
)
_CONF_URL = "https://raw.githubusercontent.com/tech-conferences/conference-data/main/conferences/{year}/{topic}.json"

# confs.tech writes some countries its own way.
_COUNTRY_ALIASES = {
    "US": {"usa", "united states", "united states of america", "us"},
    "GB": {"uk", "united kingdom", "england", "scotland", "wales", "northern ireland"},
    "AE": {"uae", "united arab emirates"},
    "KR": {"south korea", "korea", "republic of korea"},
    "CZ": {"czech republic", "czechia"},
    "NL": {"netherlands", "the netherlands"},
}


# ── helpers ────────────────────────────────────────────────────────────────

def _norm(text: Any) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", str(text or "").lower().replace(".", "")).strip()


def _f(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_day(v: Optional[str], default: date) -> date:
    try:
        return date.fromisoformat(v) if v else default
    except ValueError:
        return default


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _best_image(images: List[Dict[str, Any]]) -> Optional[str]:
    wide = [i for i in images or [] if i.get("ratio") == "16_9" and i.get("url")]
    pool = wide or [i for i in images or [] if i.get("url")]
    if not pool:
        return None
    # Smallest image at least 600px wide keeps cards light but sharp.
    pool.sort(key=lambda i: (i.get("width") or 0))
    for i in pool:
        if (i.get("width") or 0) >= 600:
            return i["url"]
    return pool[-1]["url"]


async def _get_json(session: aiohttp.ClientSession, url: str, params: Optional[dict] = None) -> Tuple[int, Any]:
    async with session.get(url, params=params) as resp:
        if resp.status != 200:
            return resp.status, None
        return 200, await resp.json(content_type=None)


# ── Ticketmaster ───────────────────────────────────────────────────────────

def _tm_category(classification: Dict[str, Any], family: bool) -> Tuple[str, Optional[str]]:
    segment = ((classification.get("segment") or {}).get("name") or "").lower()
    genre = (classification.get("genre") or {}).get("name")
    if genre and genre.lower() == "comedy":
        return "comedy", genre
    if family and segment not in ("music", "sports"):
        return "family", genre
    mapping = {"music": "music", "sports": "sports", "arts & theatre": "arts",
               "film": "film", "miscellaneous": "community"}
    sub = genre if genre and genre.lower() != "undefined" else None
    return mapping.get(segment, "community"), sub


def _tm_event(e: Dict[str, Any], origin: Optional[Tuple[float, float]]) -> Dict[str, Any]:
    venue = ((e.get("_embedded") or {}).get("venues") or [{}])[0]
    loc = venue.get("location") or {}
    vlat, vlon = _f(loc.get("latitude")), _f(loc.get("longitude"))
    start = (e.get("dates") or {}).get("start") or {}
    end = (e.get("dates") or {}).get("end") or {}
    classification = (e.get("classifications") or [{}])[0]
    category, sub = _tm_category(classification, bool(classification.get("family")))
    prices = e.get("priceRanges") or []
    price = None
    if prices:
        mins = [p.get("min") for p in prices if p.get("min") is not None]
        maxs = [p.get("max") for p in prices if p.get("max") is not None]
        price = {"min": min(mins) if mins else None, "max": max(maxs) if maxs else None,
                 "currency": prices[0].get("currency")}
    address = ", ".join(x for x in [
        (venue.get("address") or {}).get("line1"),
        (venue.get("city") or {}).get("name"),
        (venue.get("state") or {}).get("stateCode") or (venue.get("state") or {}).get("name"),
        venue.get("postalCode"),
    ] if x)
    distance = None
    if origin and vlat is not None and vlon is not None:
        distance = round(_haversine_km(origin[0], origin[1], vlat, vlon), 1)
    return {
        "id": f"tm:{e.get('id')}",
        "source": "ticketmaster",
        "title": e.get("name") or "Untitled event",
        "category": category,
        "subcategory": sub,
        "start_date": start.get("localDate"),
        "start_time": None if start.get("timeTBA") or start.get("noSpecificTime") else start.get("localTime"),
        "start_utc": start.get("dateTime"),
        "end_date": end.get("localDate"),
        "timezone": (e.get("dates") or {}).get("timezone") or venue.get("timezone"),
        "status": ((e.get("dates") or {}).get("status") or {}).get("code"),
        "online": False,
        "venue": {
            "name": venue.get("name"),
            "address": address or None,
            "city": (venue.get("city") or {}).get("name"),
            "region": (venue.get("state") or {}).get("name"),
            "country": (venue.get("country") or {}).get("name"),
            "country_code": (venue.get("country") or {}).get("countryCode"),
            "postcode": venue.get("postalCode"),
            "lat": vlat,
            "lon": vlon,
        },
        "distance_km": distance,
        "url": e.get("url"),
        "image": _best_image(e.get("images") or []),
        "price": price,
        "summary": e.get("info") or None,
    }


def _tm_detail(e: Dict[str, Any]) -> Dict[str, Any]:
    venue = ((e.get("_embedded") or {}).get("venues") or [{}])[0]
    sales = e.get("sales") or {}
    public = sales.get("public") or {}
    general = venue.get("generalInfo") or {}
    attractions = [a.get("name") for a in (e.get("_embedded") or {}).get("attractions") or [] if a.get("name")]
    return {
        "info": e.get("info"),
        "please_note": e.get("pleaseNote"),
        "performers": attractions,
        "age_restriction": (e.get("ageRestrictions") or {}).get("legalAgeEnforced"),
        "accessibility": (e.get("accessibility") or {}).get("info") or venue.get("accessibleSeatingDetail"),
        "ticket_limit": (e.get("ticketLimit") or {}).get("info"),
        "sales": {
            "public_start": public.get("startDateTime"),
            "public_end": public.get("endDateTime"),
            "presales": [
                {"name": p.get("name"), "start": p.get("startDateTime"), "end": p.get("endDateTime"),
                 "description": p.get("shortDescription") or p.get("description"), "url": p.get("url")}
                for p in sales.get("presales") or []
            ][:6],
        },
        "seatmap": (e.get("seatmap") or {}).get("staticUrl"),
        "venue_info": {
            "url": venue.get("url"),
            "parking": venue.get("parkingDetail"),
            "box_office": ((venue.get("boxOfficeInfo") or {}).get("openHoursDetail")),
            "rules": general.get("generalRule"),
            "children": general.get("childRule"),
        },
        "promoter": (e.get("promoter") or {}).get("name"),
    }


async def _ticketmaster(
    session, *, lat: float, lon: float, start: date, end: date,
    category: Optional[str], keyword: Optional[str],
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """Returns (events, radius_km_used). Widens the radius when sparse."""
    key = settings.TICKETMASTER_API_KEY
    if not key or (category and category not in _TM_CLASS):
        return [], None
    events: List[Dict[str, Any]] = []
    used = None
    for radius in _TM_RADII_KM:
        params = {
            "apikey": key,
            "latlong": f"{lat:.4f},{lon:.4f}",
            "radius": radius,
            "unit": "km",
            "size": 100,
            "sort": "date,asc",
            "startDateTime": f"{start.isoformat()}T00:00:00Z",
            "endDateTime": f"{end.isoformat()}T23:59:59Z",
        }
        if category:
            params["classificationName"] = _TM_CLASS[category]
        if keyword:
            params["keyword"] = keyword
        status, data = await _get_json(session, "https://app.ticketmaster.com/discovery/v2/events.json", params)
        if status != 200:
            logger.warning("events.ticketmaster.bad_status", status=status)
            break
        raw = ((data or {}).get("_embedded") or {}).get("events") or []
        events = [_tm_event(e, (lat, lon)) for e in raw if not e.get("test")]
        used = radius
        if len(events) >= _TM_ENOUGH:
            break
    return events, used


async def _ticketmaster_detail(event_id: str) -> Optional[Dict[str, Any]]:
    key = settings.TICKETMASTER_API_KEY
    if not key:
        return None
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        status, data = await _get_json(
            session, f"https://app.ticketmaster.com/discovery/v2/events/{event_id}.json", {"apikey": key})
    if status != 200 or not data:
        return None
    event = _tm_event(data, None)
    event["detail"] = _tm_detail(data)
    return event


# ── confs.tech ─────────────────────────────────────────────────────────────

def _conf_id(c: Dict[str, Any]) -> str:
    raw = f"{c.get('name')}|{c.get('startDate')}|{c.get('url')}"
    return "conf:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


async def _load_conferences() -> Dict[str, Dict[str, Any]]:
    """All upcoming conferences this year and next, keyed by id. Cached 12h."""
    cached = await cache.get("events.confs.index")
    if cached is not None:
        return cached
    today = date.today()
    sem = asyncio.Semaphore(8)
    by_id: Dict[str, Dict[str, Any]] = {}

    async def fetch(session, year: int, topic: str):
        async with sem:
            try:
                status, data = await _get_json(session, _CONF_URL.format(year=year, topic=topic))
            except Exception as exc:  # noqa: BLE001
                logger.warning("events.confs.error", topic=topic, error=str(exc))
                return
        for c in data or [] if status == 200 else []:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            end = c.get("endDate") or c.get("startDate")
            if not end or end < today.isoformat():
                continue
            cid = _conf_id(c)
            entry = by_id.setdefault(cid, {**c, "topics": []})
            entry["topics"].append(topic)

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        await asyncio.gather(*(fetch(session, y, t)
                               for y in (today.year, today.year + 1) for t in _CONF_TOPICS))
    if by_id:
        await cache.set("events.confs.index", by_id, ttl=12 * 3600)
    return by_id


def _country_matches(conf_country: Any, country_code: Optional[str], country: Optional[str]) -> bool:
    c = _norm(conf_country)
    if not c:
        return False
    names = set(_COUNTRY_ALIASES.get((country_code or "").upper(), set()))
    if country:
        names.add(_norm(country))
    return c in names


def _conf_event(c: Dict[str, Any], *, local: str) -> Dict[str, Any]:
    topics = [t.replace("-", " ") for t in c.get("topics") or []]
    return {
        "id": _conf_id(c),
        "source": "confs.tech",
        "title": c.get("name"),
        "category": "tech",
        "subcategory": ", ".join(t.title() if len(t) > 3 else t.upper() for t in topics[:3]) or "Conference",
        "start_date": c.get("startDate"),
        "start_time": None,
        "start_utc": None,
        "end_date": c.get("endDate"),
        "timezone": None,
        "status": "scheduled",
        # confs.tech marks hybrid events online=true and still gives a city.
        "online": bool(c.get("online")) and not c.get("city"),
        "hybrid": bool(c.get("online")) and bool(c.get("city")),
        "venue": {
            "name": None,
            "address": None,
            "city": c.get("city"),
            "region": None,
            "country": c.get("country"),
            "country_code": None,
            "postcode": None,
            "lat": None,
            "lon": None,
        },
        "distance_km": None,
        "url": c.get("url"),
        "image": None,
        "price": None,
        "summary": None,
        "locality": local,  # "city" | "country" | "online" | "elsewhere"
        "detail": {
            "cfp_url": c.get("cfpUrl"),
            "cfp_end": c.get("cfpEndDate"),
            "twitter": c.get("twitter"),
            "code_of_conduct": c.get("cocUrl"),
            "languages": c.get("locales"),
            "topics": topics,
        },
    }


async def _conferences(
    *, city: Optional[str], country_code: Optional[str], country: Optional[str],
    start: date, end: date, keyword: Optional[str], include_elsewhere: bool,
) -> List[Dict[str, Any]]:
    index = await _load_conferences()
    city_n = _norm(city)
    kw = _norm(keyword)
    out = []
    for c in index.values():
        s = c.get("startDate") or ""
        e = c.get("endDate") or s
        if e < start.isoformat() or s > end.isoformat():
            continue
        if kw and kw not in _norm(c.get("name")) and not any(kw in t for t in c.get("topics") or []):
            continue
        conf_city = _norm(c.get("city"))
        if city_n and conf_city and (conf_city.startswith(city_n) or city_n.startswith(conf_city.split(" ")[0])):
            local = "city"
        elif _country_matches(c.get("country"), country_code, country):
            local = "country"
        elif c.get("online"):
            local = "online"
        elif include_elsewhere:
            local = "elsewhere"
        else:
            continue
        out.append(_conf_event(c, local=local))
    order = {"city": 0, "country": 1, "online": 2, "elsewhere": 3}
    out.sort(key=lambda ev: (order[ev["locality"]], ev["start_date"] or ""))
    return out


# ── Public holidays ────────────────────────────────────────────────────────

async def _holidays_for(country_code: str, year: int) -> List[Dict[str, Any]]:
    key = f"events.holidays:{country_code}:{year}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            status, data = await _get_json(
                session, f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("events.holidays.error", error=str(exc))
        return []
    # 204/404 = country not covered; cache that too so we don't re-ask.
    rows = data if status == 200 and isinstance(data, list) else []
    if status in (200, 204, 404):
        await cache.set(key, rows, ttl=24 * 3600)
    return rows


def _holiday_id(h: Dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(h.get("name") or "").lower()).strip("-")
    return f"hol:{h.get('countryCode')}:{h.get('date')}:{slug}"


def _holiday_event(h: Dict[str, Any], country: Optional[str]) -> Dict[str, Any]:
    types = h.get("types") or []
    regional = not h.get("global", True)
    note = "Public holiday — many shops, banks and offices may be closed." if "Public" in types else None
    return {
        "id": _holiday_id(h),
        "source": "nager.date",
        "title": h.get("name") if h.get("name") == h.get("localName") else f"{h.get('name')} ({h.get('localName')})",
        "category": "holiday",
        "subcategory": "Regional holiday" if regional else ", ".join(t.replace("Public", "Public holiday") for t in types) or "Holiday",
        "start_date": h.get("date"),
        "start_time": None,
        "start_utc": None,
        "end_date": h.get("date"),
        "timezone": None,
        "status": "scheduled",
        "online": False,
        "venue": {"name": None, "address": None, "city": None, "region": None,
                  "country": country, "country_code": h.get("countryCode"),
                  "postcode": None, "lat": None, "lon": None},
        "distance_km": None,
        "url": None,
        "image": None,
        "price": None,
        "summary": note,
        "detail": {"local_name": h.get("localName"), "regions": h.get("counties"),
                   "types": types, "since": h.get("launchYear")},
    }


async def _holidays(*, country_code: Optional[str], country: Optional[str],
                    start: date, end: date, keyword: Optional[str]) -> List[Dict[str, Any]]:
    if not country_code:
        return []
    rows: List[Dict[str, Any]] = []
    for year in sorted({start.year, end.year}):
        rows += await _holidays_for(country_code.upper(), year)
    kw = _norm(keyword)
    out = []
    for h in rows:
        d = h.get("date") or ""
        if start.isoformat() <= d <= end.isoformat():
            if kw and kw not in _norm(h.get("name")) and kw not in _norm(h.get("localName")):
                continue
            out.append(_holiday_event(h, country))
    return out


# ── Service ────────────────────────────────────────────────────────────────

_CACHED_DETAIL_PREFIXES = {"luma", "devpost", "mlh", "devev"}
_DETAIL_TTL_S = 14 * 24 * 3600


def _dedupe(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Same event from several sources (title + start date + city): keep the
    first, i.e. the richer source (Luma/Devpost/MLH before confs.tech)."""
    seen = set()
    out = []
    for e in events:
        key = (_norm_title(e.get("title")), e.get("start_date"), _norm_title((e.get("venue") or {}).get("city")))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


class EventsService:
    async def search(
        self,
        *,
        lat: float,
        lon: float,
        city: Optional[str] = None,
        country_code: Optional[str] = None,
        country: Optional[str] = None,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        keyword: Optional[str] = None,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        today = date.today()
        start = _parse_day(date_from, today)
        end = _parse_day(date_to, start + timedelta(days=30))
        if end < start:
            end = start
        end = min(end, start + timedelta(days=366))
        category = category if category in CATEGORIES else None
        keyword = (keyword or "").strip()[:80] or None

        cache_key = (f"events.search:{lat:.2f}:{lon:.2f}:{(country_code or '').upper()}:"
                     f"{category}:{start}:{end}:{(keyword or '').lower()}")
        cached = await cache.get(cache_key)
        if cached is not None:
            return cached

        want_tm = category is None or category in _TM_CLASS
        want_tech = category in (None, "tech")
        want_hol = category in (None, "holiday")

        async def tm():
            if not want_tm:
                return [], None
            try:
                async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                    return await _ticketmaster(session, lat=lat, lon=lon, start=start, end=end,
                                               category=category, keyword=keyword)
            except Exception as exc:  # noqa: BLE001
                logger.warning("events.ticketmaster.error", error=str(exc))
                return [], None

        async def tech():
            if not want_tech:
                return []
            try:
                return await _conferences(city=city, country_code=country_code, country=country,
                                          start=start, end=end, keyword=keyword,
                                          include_elsewhere=category == "tech")
            except Exception as exc:  # noqa: BLE001
                logger.warning("events.confs.error", error=str(exc))
                return []

        async def hol():
            if not want_hol:
                return []
            return await _holidays(country_code=country_code, country=country,
                                   start=start, end=end, keyword=keyword)

        want_sources = category in (None, "tech", "community")

        async def sources():
            """Luma, Devpost, MLH, dev.events: each fail-soft on its own."""
            if not want_sources:
                return []
            sq = SourceQuery(lat=lat, lon=lon, city=city, region=region, country=country,
                             country_code=country_code, start=start, end=end, keyword=keyword)
            batches = await asyncio.gather(*(src.safe_fetch(sq) for src in TECH_SOURCES))
            kw = _norm_title(keyword) if keyword else None
            out = []
            for e in (e for batch in batches for e in batch):
                if category and e["category"] != category:
                    continue
                if kw and kw not in _norm_title(e["title"]):
                    continue
                out.append(e)
            return out

        (tm_events, radius), conf_events, hol_events, src_events = await asyncio.gather(
            tm(), tech(), hol(), sources())
        conf_events = _dedupe(src_events + conf_events)

        if category is None:
            # In the mixed view, keep local tech/community events but only a
            # handful of online/far-away ones so they don't drown out local events.
            local = [e for e in conf_events if e["locality"] == "city"]
            remote = [e for e in conf_events if e["locality"] != "city"]
            conf_events = local + remote[:_ONLINE_IN_MIXED]

        events = tm_events + conf_events + hol_events
        events.sort(key=lambda e: (e.get("start_date") or "9999", e.get("start_time") or "99"))
        counts: Dict[str, int] = {}
        for e in events:
            counts[e["category"]] = counts.get(e["category"], 0) + 1

        result = {
            "events": events,
            "counts": counts,
            "window": {"from": start.isoformat(), "to": end.isoformat()},
            "radius_km": radius,
            "sources": sorted({e["source"] for e in events}),
            "coverage_note": self._coverage_note(tm_events, radius, want_tm, city,
                                                 category=category, others=conf_events + hol_events),
        }
        # Remember source events so their detail pages can be served
        # (these sources have no per-event lookup endpoint we use). Kept two
        # weeks: people open them again from their events and reminders.
        for e in conf_events:
            if e["id"].split(":", 1)[0] in _CACHED_DETAIL_PREFIXES:
                await cache.set(f"events.item:{e['id']}", e, ttl=_DETAIL_TTL_S)
        # Only cache answers that found something; empty results are often
        # transient (rate limits, timeouts).
        if events:
            await cache.set(cache_key, result, ttl=600)
        return result

    @staticmethod
    def _coverage_note(tm_events, radius, want_tm, city, *, category=None, others=()) -> Optional[str]:
        """Positive, specific note about coverage. None when nothing to say."""
        where = city or "this area"
        local_others = [e for e in others if e.get("locality") == "city"]
        if category in ("tech", "community"):
            if not local_others:
                return (f"No in-person {'tech' if category == 'tech' else 'community'} events "
                        f"are listed in {where} for these dates. The online ones below are "
                        "open to everyone, and nearby cities may have more.")
            return None
        if want_tm and not tm_events:
            if local_others:
                return (f"Big ticketed shows aren't listed for {where} yet, so here are local "
                        "meetups, community events and holidays instead.")
            return (f"Local listings for {where} are thin right now. Here's what's online "
                    "and coming up nationally; local venues and tourist offices often list more.")
        if radius and radius > _TM_RADII_KM[0]:
            return f"Few ticketed shows right in {where}, so we searched up to {radius} km away."
        return None

    async def detail(self, event_id: str) -> Optional[Dict[str, Any]]:
        if event_id.split(":", 1)[0] in _CACHED_DETAIL_PREFIXES:
            return await cache.get(f"events.item:{event_id}")
        if event_id.startswith("tm:"):
            return await _ticketmaster_detail(event_id[3:])
        if event_id.startswith("conf:"):
            c = (await _load_conferences()).get(event_id)
            return _conf_event(c, local="elsewhere") if c else None
        if event_id.startswith("hol:"):
            parts = event_id.split(":", 3)
            if len(parts) != 4:
                return None
            _, cc, day, _slug = parts
            try:
                year = date.fromisoformat(day).year
            except ValueError:
                return None
            for h in await _holidays_for(cc.upper(), year):
                if _holiday_id(h) == event_id:
                    return _holiday_event(h, None)
        return None


events_service = EventsService()
