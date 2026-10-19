"""
Map services: directions with route geometry and turn-by-turn steps (drive,
walk, bike, transit), and nearby places by category for the map's quick
filters ("Restaurants", "Pharmacies", "ATMs", ...).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp

from apps.api.core.config import settings
from apps.api.core.throttle import NominatimBusy, nominatim_slot
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import PlaceRef, distance_m, nearby

logger = get_logger(__name__)

ROUTING_URL = "https://api.geoapify.com/v1/routing"
TIMEOUT = aiohttp.ClientTimeout(total=12)

# Navis mode → Geoapify mode
MODES = {"drive": "drive", "walk": "walk", "bike": "bicycle", "transit": "approximated_transit"}

# Map quick filters → Geoapify categories
CATEGORIES: Dict[str, Dict[str, str]] = {
    "restaurants": {"label": "Restaurants", "category": "catering.restaurant"},
    "cafes": {"label": "Coffee", "category": "catering.cafe"},
    "groceries": {"label": "Groceries", "category": "commercial.supermarket,commercial.convenience"},
    "pharmacies": {"label": "Pharmacies", "category": "healthcare.pharmacy"},
    "hospitals": {"label": "Hospitals", "category": "healthcare.hospital"},
    "atms": {"label": "ATMs & banks", "category": "service.financial.atm,service.financial.bank"},
    "transit": {"label": "Transit", "category": "public_transport"},
    "hotels": {"label": "Hotels", "category": "accommodation.hotel,accommodation.guest_house,accommodation.hostel"},
    "attractions": {"label": "Things to do", "category": "tourism.attraction,tourism.sights,entertainment.museum"},
    "parks": {"label": "Parks", "category": "leisure.park"},
    "gas": {"label": "Gas & charging", "category": "service.vehicle.fuel,service.vehicle.charging_station"},
    "parking": {"label": "Parking", "category": "parking"},
}


def _flatten(geometry: Dict[str, Any]) -> List[List[float]]:
    coords = geometry.get("coordinates") or []
    if geometry.get("type") == "LineString":
        return [list(c) for c in coords]
    return [list(c) for line in coords for c in line]


async def _route_one(session: aiohttp.ClientSession, origin, dest, mode: str) -> Optional[Dict[str, Any]]:
    params = {"waypoints": f"{origin[0]},{origin[1]}|{dest[0]},{dest[1]}", "mode": MODES[mode],
              "details": "instruction_details", "apiKey": settings.GEOAPIFY_API_KEY}
    try:
        async with session.get(ROUTING_URL, params=params) as resp:
            if resp.status != 200:
                logger.info("maps.route.bad_status", status=resp.status, mode=mode)
                return None
            data = await resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("maps.route.error", mode=mode, error=str(exc))
        return None
    feats = data.get("features") or []
    if not feats:
        return None
    props = feats[0].get("properties") or {}
    steps = []
    for leg in props.get("legs") or []:
        for st in leg.get("steps") or []:
            text = (st.get("instruction") or {}).get("text")
            if text:
                steps.append({"instruction": text, "distance_m": st.get("distance"), "time_s": st.get("time")})
    return {
        "mode": mode,
        "distance_km": round(float(props.get("distance") or 0) / 1000, 2),
        "duration_min": round(float(props.get("time") or 0) / 60, 1),
        "geometry": _flatten(feats[0].get("geometry") or {}),
        "steps": steps[:60],
    }


# ── public transit: real timetables + live delays (MOTIS / Transitous) ─────

_TRANSIT_UA = {"User-Agent": "Navis/1.0 (city companion; https://navis.app)"}
_TRANSIT_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)
_TRANSIT_WORDS = {"BUS": "bus", "TRAM": "tram", "SUBWAY": "subway", "RAIL": "train", "REGIONAL_RAIL": "train",
                  "HIGHSPEED_RAIL": "train", "LONG_DISTANCE": "train", "NIGHT_RAIL": "night train", "METRO": "metro",
                  "COACH": "coach", "FERRY": "ferry", "AIRPLANE": "flight", "CABLE_CAR": "cable car",
                  "FUNICULAR": "funicular", "AERIAL_LIFT": "cable car", "SUBURBAN": "train", "TROLLEYBUS": "trolleybus"}


def decode_polyline(points: str, precision: int = 5) -> List[List[float]]:
    """Google encoded polyline → [[lon, lat], ...]."""
    coords, index, lat, lon = [], 0, 0, 0
    factor = 10 ** precision
    while index < len(points):
        for is_lon in (False, True):
            shift = result = 0
            while True:
                b = ord(points[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lon:
                lon += delta
            else:
                lat += delta
        coords.append([lon / factor, lat / factor])
    return coords


def _active_alerts(stop: Dict[str, Any], now: float) -> List[str]:
    out = []
    for alert in stop.get("alerts") or []:
        periods = alert.get("impactPeriod") or alert.get("communicationPeriod") or []
        active = not periods
        for period in periods:
            try:
                start = datetime.fromisoformat(period["start"].replace("Z", "+00:00")).timestamp()
                end = datetime.fromisoformat(period["end"].replace("Z", "+00:00")).timestamp()
            except (KeyError, ValueError):
                continue
            active = active or start <= now <= end
        if active and alert.get("headerText"):
            out.append(alert["headerText"][:240])
    return out


def _itinerary_to_route(it: Dict[str, Any]) -> Dict[str, Any]:
    legs = [leg for leg in it.get("legs") or [] if not leg.get("cancelled")]
    geometry: List[List[float]] = []
    steps: List[Dict[str, Any]] = []
    lines: List[Dict[str, Any]] = []
    alerts: List[str] = []
    now = datetime.now(timezone.utc).timestamp()
    distance = 0.0
    for leg in legs:
        geom = leg.get("legGeometry") or {}
        if geom.get("points"):
            geometry.extend(decode_polyline(geom["points"], int(geom.get("precision") or 5)))
        to_name = (leg.get("to") or {}).get("name") or "your destination"
        if to_name == "END":
            to_name = "your destination"
        mode = leg.get("mode") or ""
        if mode in ("WALK", "BIKE", "CAR", "RENTAL", "SCOOTER"):
            dist = float(leg.get("distance") or 0)
            distance += dist
            verb = {"WALK": "Walk", "BIKE": "Cycle", "RENTAL": "Ride a shared bike/scooter"}.get(mode, "Drive")
            steps.append({"instruction": f"{verb} to {to_name}", "distance_m": round(dist), "time_s": leg.get("duration")})
            continue
        word = _TRANSIT_WORDS.get(mode, "transit")
        name = leg.get("displayName") or leg.get("routeShortName") or leg.get("routeLongName") or word
        frm = (leg.get("from") or {}).get("name") or "the stop"
        stops = len(leg.get("intermediateStops") or []) + 1
        headsign = leg.get("headsign")
        text = f"Take the {name} {word}" if word not in name.lower() else f"Take the {name}"
        if headsign:
            text += f" toward {headsign}"
        text += f" from {frm}, {stops} stop{'s' if stops != 1 else ''} to {to_name}"
        steps.append({"instruction": text, "time_s": leg.get("duration"),
                      "departure": leg.get("startTime"), "realtime": bool(leg.get("realTime"))})
        lines.append({"name": name, "mode": word, "color": f"#{leg['routeColor']}" if leg.get("routeColor") else None,
                      "text_color": f"#{leg['routeTextColor']}" if leg.get("routeTextColor") else None,
                      "agency": leg.get("agencyName"), "url": leg.get("routeUrl"),
                      "departure": leg.get("startTime"), "from": frm, "realtime": bool(leg.get("realTime"))})
        for stop in (leg.get("from") or {}, leg.get("to") or {}):
            for a in _active_alerts(stop, now):
                if a not in alerts:
                    alerts.append(a)
    return {
        "mode": "transit",
        "distance_km": round(distance / 1000, 2) if distance else 0.0,
        "duration_min": round(float(it.get("duration") or 0) / 60, 1),
        "geometry": geometry,
        "steps": steps[:60],
        "lines": lines,
        "transfers": it.get("transfers"),
        "departure": it.get("startTime"),
        "arrival": it.get("endTime"),
        "timezone": next(((leg.get("from") or {}).get("tz") for leg in legs if (leg.get("from") or {}).get("tz")), None),
        "alerts": alerts[:3],
        "source": "timetable",
    }


async def _transitous(session: aiohttp.ClientSession, origin, dest) -> Optional[Dict[str, Any]]:
    params = {"fromPlace": f"{origin[0]},{origin[1]}", "toPlace": f"{dest[0]},{dest[1]}", "numItineraries": "4"}
    try:
        async with session.get(f"{settings.TRANSIT_ROUTING_URL}/api/v1/plan", params=params,
                               headers=_TRANSIT_UA, timeout=_TRANSIT_TIMEOUT) as resp:
            if resp.status != 200:
                logger.info("maps.transit.bad_status", status=resp.status)
                return None
            data = await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        logger.info("maps.transit.error", error=type(exc).__name__)
        return None
    itineraries = [it for it in data.get("itineraries") or []
                   if any(leg.get("mode") not in ("WALK", "BIKE", "CAR") for leg in it.get("legs") or [])]
    if not itineraries:
        return None
    best = min(itineraries, key=lambda it: (it.get("endTime") or "", it.get("duration") or 0))
    return _itinerary_to_route(best)


async def _transit(session: aiohttp.ClientSession, origin, dest) -> Optional[Dict[str, Any]]:
    """Real timetable routing first; the estimate-based router as a fallback."""
    return await _transitous(session, origin, dest) or await _route_one(session, origin, dest, "transit")


async def directions(origin: tuple, dest: tuple, modes: List[str]) -> Dict[str, Any]:
    """Routes for each requested mode, fastest first. Missing modes are
    simply absent (e.g. no transit data for that area)."""
    if not settings.GEOAPIFY_API_KEY:
        return {"routes": [], "message": "Directions aren't available right now."}
    modes = [m for m in modes if m in MODES] or list(MODES)
    key = f"maps.route:{origin[0]:.5f},{origin[1]:.5f}:{dest[0]:.5f},{dest[1]:.5f}:{','.join(sorted(modes))}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        found = await asyncio.gather(*(
            _transit(session, origin, dest) if m == "transit" else _route_one(session, origin, dest, m)
            for m in modes))
    routes = [r for r in found if r]
    missing = [m for m, r in zip(modes, found) if not r]
    message = None
    if not routes:
        message = "We couldn't find a route between those places. Try points closer to a road or path."
    elif "transit" in missing:
        message = "Public transit directions aren't available for this trip; here are the other options."
    out = {"routes": routes, "message": message}
    if routes:
        # Timetable results carry departure times and live delays: keep them short-lived.
        live = any(r.get("source") == "timetable" for r in routes)
        await cache.set(key, out, ttl=3 * 60 if live else 30 * 60)
    return out


async def places_by_category(place: PlaceRef, category: str, *, radius_m: int = 3000, limit: int = 40) -> Dict[str, Any]:
    spec = CATEGORIES.get(category)
    if not spec:
        return {"items": [], "message": "Unknown category."}
    found = await nearby(place, spec["category"], radius_m=radius_m, limit=limit)
    if found is None:
        return {"items": [], "message": f"{spec['label']} aren't loading right now. Try again in a moment."}
    if not found:
        return {"items": [], "message": f"No {spec['label'].lower()} are mapped within {radius_m // 1000} km. "
                                        "Try zooming out or searching a nearby area."}
    return {"items": found, "message": None}


# ── place details (tapping a shop or landmark on the base map) ─────────────

PLACES_URL = "https://api.geoapify.com/v2/places"
WIKI_SUMMARY = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
# Broad enough to cover anything the map labels as a POI.
_POI_CATEGORIES = ("commercial,catering,tourism,entertainment,healthcare,service,leisure,accommodation,"
                   "education,religion,amenity,public_transport,building.historic,heritage,office,sport,"
                   "childcare,parking,rental,airport,natural,national_park,camping,beach,activity")
_LANDMARK_PREFIXES = ("tourism", "heritage", "religion", "entertainment.museum", "entertainment.culture",
                      "building.historic", "national_park", "natural")
_EXTRA_TAGS = ("cuisine", "brand", "wheelchair", "outdoor_seating", "takeaway", "delivery", "diet:vegetarian",
               "internet_access", "payment:credit_cards", "level", "operator", "denomination", "fee", "start_date",
               "architect", "heritage")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _name_score(a: str, b: str) -> float:
    ta, tb = set(_norm(a).split()), set(_norm(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


async def _wiki(session: aiohttp.ClientSession, ref: Optional[str], name: str, lat: float, lon: float,
                landmark: bool) -> Optional[Dict[str, Any]]:
    """Summary + photo for a landmark: from its OSM wikipedia tag, or (for
    landmarks only) a same-name article whose coordinates are within 1 km."""
    lang, title, check_coords = "en", None, False
    if ref and ":" in ref:
        lang, title = ref.split(":", 1)
    elif landmark and name:
        title, check_coords = name, True
    if not title or not re.fullmatch(r"[a-z]{2,3}", lang):
        return None
    url = WIKI_SUMMARY.format(lang=lang, title=quote(title.replace(" ", "_"), safe=""))
    try:
        async with session.get(url, headers={"User-Agent": "Navis/1.0 (city companion)"}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
    except Exception:  # noqa: BLE001
        return None
    if data.get("type") == "disambiguation" or not data.get("extract"):
        return None
    coords = data.get("coordinates") or {}
    if check_coords and (not coords or distance_m(lat, lon, coords.get("lat", 0), coords.get("lon", 0)) > 1000):
        return None
    return {
        "extract": data["extract"],
        "image": ((data.get("thumbnail") or data.get("originalimage")) or {}).get("source"),
        "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page"),
    }


_UA = {"User-Agent": "Navis/1.0 (city companion; https://navis.app)"}


async def _nominatim(session: aiohttp.ClientSession, lat: float, lon: float, name: str) -> Optional[Dict[str, Any]]:
    d = 0.006
    params = {"q": name, "viewbox": f"{lon - d},{lat + d},{lon + d},{lat - d}", "bounded": "1",
              "format": "jsonv2", "extratags": "1", "addressdetails": "1", "limit": "5"}
    try:
        await nominatim_slot()
    except NominatimBusy:
        return None
    try:
        async with session.get(f"{settings.NOMINATIM_URL}/search", params=params, headers=_UA) as resp:
            rows = await resp.json(content_type=None) if resp.status == 200 else []
    except Exception as exc:  # noqa: BLE001
        logger.info("maps.place.nominatim_error", error=type(exc).__name__)
        rows = []
    best, best_score = None, 0.0
    for r in rows or []:
        try:
            rl, rn = float(r["lat"]), float(r["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        score = _name_score(name, r.get("name") or "") - distance_m(lat, lon, rl, rn) / 2000
        if score > best_score:
            best, best_score = r, score
    if not best or _name_score(name, best.get("name") or "") < 0.5:
        return None
    tags = best.get("extratags") or {}
    cat = f"{best.get('category')}.{best.get('type')}"
    return {
        "name": best.get("name") or name,
        "address": _short_address(best.get("address") or {}) or best.get("display_name"),
        "categories": [best.get("category"), cat],
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "website": tags.get("website") or tags.get("contact:website") or tags.get("url"),
        "opening_hours": tags.get("opening_hours"),
        "attributes": {k: str(tags[k]) for k in _EXTRA_TAGS if k in tags},
        "landmark": best.get("category") in ("tourism", "historic", "heritage") or cat in _LANDMARK_TYPES,
        "_wikipedia": tags.get("wikipedia"),
        "_wikidata": tags.get("wikidata"),
    }


_LANDMARK_TYPES = {"amenity.place_of_worship", "leisure.park", "amenity.theatre", "amenity.arts_centre",
                   "leisure.stadium", "amenity.university", "building.cathedral", "man_made.tower",
                   "natural.peak", "leisure.garden"}


def _short_address(a: Dict[str, str]) -> str:
    street = " ".join(x for x in (a.get("house_number"), a.get("road")) if x)
    area = a.get("neighbourhood") or a.get("suburb") or a.get("quarter")
    city = a.get("city") or a.get("town") or a.get("village")
    parts = [street, area, city, a.get("state"), a.get("postcode")]
    return ", ".join(dict.fromkeys(p for p in parts if p))


async def _geoapify_poi(session: aiohttp.ClientSession, lat: float, lon: float, name: str) -> Optional[Dict[str, Any]]:
    params = {"categories": _POI_CATEGORIES, "filter": f"circle:{lon},{lat},150",
              "bias": f"proximity:{lon},{lat}", "limit": "20", "apiKey": settings.GEOAPIFY_API_KEY}
    try:
        async with session.get(PLACES_URL, params=params) as resp:
            feats = ((await resp.json()).get("features") or []) if resp.status == 200 else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("maps.place.error", error=str(exc))
        return None
    best, best_score = None, 0.0
    for f in feats:
        p = f.get("properties") or {}
        if p.get("lat") is None:
            continue
        near = 1 - distance_m(lat, lon, p["lat"], p["lon"]) / 150
        score = _name_score(name, p.get("name") or "") + 0.1 * near if name else near
        if score > best_score:
            best, best_score = p, score
    if not best or (name and _name_score(name, best.get("name") or "") < 0.6):
        return None
    if not name and distance_m(lat, lon, best["lat"], best["lon"]) > 40:
        return None
    raw = (best.get("datasource") or {}).get("raw") or {}
    cats = best.get("categories") or []
    contact = best.get("contact") or {}
    return {
        "name": best.get("name") or name or best.get("address_line1"),
        "address": best.get("formatted") or best.get("address_line2"),
        "categories": cats,
        "lat": best["lat"],
        "lon": best["lon"],
        "phone": contact.get("phone") or raw.get("phone") or raw.get("contact:phone"),
        "website": best.get("website") or raw.get("website") or raw.get("contact:website"),
        "opening_hours": best.get("opening_hours") or raw.get("opening_hours"),
        "attributes": {k: str(raw[k]) for k in _EXTRA_TAGS if k in raw},
        "landmark": any(c.startswith(_LANDMARK_PREFIXES) for c in cats),
        "_wikipedia": raw.get("wikipedia"),
        "_wikidata": raw.get("wikidata"),
    }


async def _enwiki_from_wikidata(session: aiohttp.ClientSession, qid: str) -> Optional[str]:
    if not re.fullmatch(r"Q[0-9]{1,12}", qid or ""):
        return None
    params = {"action": "wbgetentities", "ids": qid, "props": "sitelinks", "sitefilter": "enwiki", "format": "json"}
    try:
        async with session.get("https://www.wikidata.org/w/api.php", params=params, headers=_UA) as resp:
            data = await resp.json(content_type=None) if resp.status == 200 else {}
    except Exception:  # noqa: BLE001
        return None
    title = (((data.get("entities") or {}).get(qid) or {}).get("sitelinks") or {}).get("enwiki", {}).get("title")
    return f"en:{title}" if title else None


async def place_details(lat: float, lon: float, name: str = "") -> Dict[str, Any]:
    """Details for a shop or landmark the user tapped on the map: address,
    phone, website, hours, a few useful attributes and, for landmarks, a
    short description with a photo. The map's own data is OpenStreetMap, so
    the OSM search finds the same feature; the places API is the fallback.
    Without a match: just the name and point."""
    base = {"name": name or "Dropped pin", "lat": lat, "lon": lon}
    key = f"maps.place:{lat:.5f},{lon:.5f}:{_norm(name)}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    place = None
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        if name:
            place = await _nominatim(session, lat, lon, name)
        if not place and settings.GEOAPIFY_API_KEY:
            place = await _geoapify_poi(session, lat, lon, name)
        if place:
            ref = place.pop("_wikipedia", None)
            qid = place.pop("_wikidata", None)
            if not ref and qid:
                ref = await _enwiki_from_wikidata(session, qid)
            place["about"] = await _wiki(session, ref, place["name"],
                                         place["lat"], place["lon"], place["landmark"])
    out = {"place": place or base}
    await cache.set(key, out, ttl=12 * 3600)
    return out
