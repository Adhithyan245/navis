"""
Live public transit (MOTIS / Transitous, free, worldwide where agencies
publish GTFS-Realtime):

  nearby_stops()   transit stops around a point, nearest first
  departures()     the next departures at a stop, with live delays,
                   cancellations and platforms
  nearby_boards()  departure boards for the closest few stops
  vehicles()       every vehicle moving through a map area in the next
                   couple of minutes, as path segments with times; the map
                   interpolates positions along them to animate vehicles
  trip()           one vehicle's trip: where it is now, the stops ahead with
                   live arrival times, and when it reaches the rider's stop

Where an agency has no live feed, times are the published timetable
(`realtime: false`), so the UI can label them "scheduled".
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from apps.api.core.config import settings
from apps.api.core.http import get_session
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import distance_m
from apps.api.services.domain.maps import _TRANSIT_WORDS, decode_polyline

logger = get_logger(__name__)

_UA = {"User-Agent": "Navis/1.0 (city companion; https://navis.app)"}
_TIMEOUT = aiohttp.ClientTimeout(total=12, connect=5)
MAX_VEHICLES = 400
# Boards show what's coming soon; a stop served once a day would otherwise list the next week.
BOARD_HORIZON = timedelta(hours=6)
MAX_BBOX_DEG = 0.25          # ~25 km across; wider views get no vehicles (too many to draw)


async def _get(path: str, params: Dict[str, Any]) -> Optional[Any]:
    try:
        async with get_session().get(f"{settings.TRANSIT_ROUTING_URL}{path}", params=params,
                                     headers=_UA, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                logger.info("live_transit.bad_status", path=path, status=resp.status)
                return None
            return await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        logger.info("live_transit.error", path=path, error=type(exc).__name__)
        return None


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _delay_min(actual: Optional[str], scheduled: Optional[str]) -> Optional[int]:
    a, s = _parse(actual), _parse(scheduled)
    if not a or not s:
        return None
    return round((a - s).total_seconds() / 60)


def _color(hex_value: Optional[str]) -> Optional[str]:
    return f"#{hex_value}" if hex_value else None


# ── stops ──────────────────────────────────────────────────────────────────

async def nearby_stops(lat: float, lon: float, *, radius_m: int = 600, limit: int = 8) -> Optional[List[Dict[str, Any]]]:
    key = f"live.stops:{lat:.4f}:{lon:.4f}:{radius_m}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    d_lat = radius_m / 111_000
    d_lon = radius_m / (111_000 * max(0.2, math.cos(math.radians(lat))))
    data = await _get("/api/v1/map/stops", {"min": f"{lat - d_lat},{lon - d_lon}", "max": f"{lat + d_lat},{lon + d_lon}"})
    if data is None:
        return None
    seen: Dict[str, Dict[str, Any]] = {}
    for s in data if isinstance(data, list) else []:
        try:
            d = distance_m(lat, lon, float(s["lat"]), float(s["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d > radius_m or not s.get("stopId"):
            continue
        name = s.get("name") or "Stop"
        # Several platforms share a name; keep the closest and remember its modes.
        modes = sorted({_TRANSIT_WORDS.get(m, m.lower()) for m in s.get("modes") or []})
        prev = seen.get(name)
        if prev is None or d < prev["distance_m"]:
            seen[name] = {"stop_id": s["stopId"], "name": name, "lat": s["lat"], "lon": s["lon"],
                          "distance_m": round(d), "modes": sorted(set(modes) | set(prev["modes"] if prev else []))}
        else:
            prev["modes"] = sorted(set(prev["modes"]) | set(modes))
    out = sorted(seen.values(), key=lambda s: s["distance_m"])[:limit]
    await cache.set(key, out, ttl=6 * 3600)
    return out


# ── departures ─────────────────────────────────────────────────────────────

def _line_name(st: Dict[str, Any], word: str) -> str:
    # Trips added by the realtime feed can carry "?" or nothing as their name.
    for k in ("displayName", "routeShortName", "routeLongName"):
        v = (st.get(k) or "").strip()
        if v and v != "?":
            return v
    return word.capitalize()


def _departure_row(st: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    place = st.get("place") or {}
    # Arrival-only rows are trips ending here: nobody can board them.
    when = place.get("departure")
    if not when:
        return None
    word = _TRANSIT_WORDS.get(st.get("mode") or "", "transit")
    return {
        "line": _line_name(st, word),
        "mode": word,
        "headsign": st.get("headsign"),
        "color": _color(st.get("routeColor")),
        "text_color": _color(st.get("routeTextColor")),
        "agency": st.get("agencyName"),
        "departure": when,
        "scheduled": place.get("scheduledDeparture"),
        "delay_min": _delay_min(when, place.get("scheduledDeparture")),
        "realtime": bool(st.get("realTime")),
        "cancelled": bool(st.get("cancelled") or st.get("tripCancelled")),
        "platform": place.get("track"),
        "route_url": st.get("routeUrl"),
        "trip_id": st.get("tripId"),
    }


async def departures(stop_id: str, *, n: int = 10) -> Optional[Dict[str, Any]]:
    key = f"live.deps:{stop_id}:{n}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    data = await _get("/api/v1/stoptimes", {"stopId": stop_id, "n": str(max(1, min(n, 30)))})
    if data is None:
        return None
    rows, seen = [], set()
    horizon = datetime.now(timezone.utc) + BOARD_HORIZON
    for st in data.get("stopTimes") or []:
        row = _departure_row(st)
        when = _parse(row["departure"]) if row else None
        if when and when > horizon:
            continue
        # Feeds can list one departure several times (shared platforms, merged trips).
        ident = (row["line"], row["headsign"], row["departure"]) if row else None
        if row and ident not in seen:
            seen.add(ident)
            rows.append(row)
    rows.sort(key=lambda r: r["departure"])
    place = data.get("place") or {}
    out = {"stop_id": stop_id, "name": place.get("name"), "timezone": place.get("tz"),
           "departures": rows, "live": any(r["realtime"] for r in rows)}
    await cache.set(key, out, ttl=30)          # live data: refresh often
    return out


async def nearby_boards(lat: float, lon: float, *, stops: int = 3, n: int = 6) -> Dict[str, Any]:
    found = await nearby_stops(lat, lon)
    if found is None:
        return {"stops": [], "message": "Live transit isn't loading right now. Try again in a moment."}
    if not found:
        return {"stops": [], "message": "There are no transit stops within a few minutes' walk. "
                                         "Try the map, or search a nearby station."}
    picked = found[:stops]
    boards = await asyncio.gather(*(departures(s["stop_id"], n=n) for s in picked))
    out = []
    for stop, board in zip(picked, boards):
        out.append({**stop, "timezone": (board or {}).get("timezone"),
                    "departures": (board or {}).get("departures") or [],
                    "live": bool((board or {}).get("live"))})
    message = None
    if out and not any(s["departures"] for s in out):
        message = "No departures from nearby stops in the next few hours. Service may have finished for the day."
    elif out and not any(s["live"] for s in out):
        message = "This area's operators don't share live positions, so times shown are the published timetable."
    return {"stops": out, "message": message}


# ── vehicles ───────────────────────────────────────────────────────────────

async def vehicles(min_lat: float, min_lon: float, max_lat: float, max_lon: float, *,
                   zoom: float = 14, window_s: int = 150) -> Dict[str, Any]:
    if (max_lat - min_lat) > MAX_BBOX_DEG or (max_lon - min_lon) > MAX_BBOX_DEG / max(0.2, math.cos(math.radians(min_lat))):
        return {"vehicles": [], "message": "Zoom in to see vehicles moving live.", "too_wide": True}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    # Round the box so nearby viewers share one upstream call.
    key = f"live.veh:{min_lat:.3f}:{min_lon:.3f}:{max_lat:.3f}:{max_lon:.3f}:{int(zoom)}:{int(now.timestamp() // 20)}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    data = await _get("/api/v1/map/trips", {
        "min": f"{min_lat},{min_lon}", "max": f"{max_lat},{max_lon}", "zoom": str(int(zoom)),
        "startTime": _iso(now - timedelta(seconds=30)), "endTime": _iso(now + timedelta(seconds=window_s)),
    })
    if data is None:
        return {"vehicles": [], "message": "Live vehicles aren't loading right now."}
    out = []
    for seg in data if isinstance(data, list) else []:
        dep, arr = seg.get("departure"), seg.get("arrival")
        if not dep or not arr or not seg.get("polyline"):
            continue
        path = decode_polyline(seg["polyline"], 5)
        if len(path) < 2:
            continue
        trip = (seg.get("trips") or [{}])[0]
        out.append({
            "id": trip.get("tripId") or f"{dep}:{path[0]}",
            "line": _line_name(trip, _TRANSIT_WORDS.get(seg.get("mode") or "", "transit")),
            "mode": _TRANSIT_WORDS.get(seg.get("mode") or "", "transit"),
            "color": _color(seg.get("routeColor")) or "#4f46e5",
            "headsign": (seg.get("to") or {}).get("name"),
            "from": (seg.get("from") or {}).get("name"),
            "to": (seg.get("to") or {}).get("name"),
            "departure": dep,
            "arrival": arr,
            "delay_min": _delay_min(dep, seg.get("scheduledDeparture")),
            "realtime": bool(seg.get("realTime")),
            "path": path,
        })
        if len(out) >= MAX_VEHICLES:
            break
    result = {"vehicles": out, "server_time": _iso(now),
              "message": None if out else "No vehicles are moving in this area right now."}
    await cache.set(key, result, ttl=20)
    return result


# ── one trip (track a vehicle) ─────────────────────────────────────────────

TRIP_STOPS_AHEAD = 15
MAX_PATH_POINTS = 1500
_STOP_SEARCH_WINDOW = 800    # geometry points searched ahead of the previous stop
_NEAR_DEG2 = (80 / 111_000) ** 2   # a path point within ~80 m is this stop


def _stop_row(s: Dict[str, Any]) -> Dict[str, Any]:
    arrival = s.get("arrival") or s.get("departure")
    scheduled = s.get("scheduledArrival") or s.get("scheduledDeparture")
    return {
        "name": s.get("name") or "Stop",
        "stop_id": s.get("stopId"),
        "parent_id": s.get("parentId"),
        "lat": s.get("lat"),
        "lon": s.get("lon"),
        "arrival": arrival,
        "departure": s.get("departure") or arrival,
        "scheduled": scheduled,
        "delay_min": _delay_min(arrival, scheduled),
        "cancelled": bool(s.get("cancelled")),
    }


def _stop_indices(path: List[List[float]], stops: List[Dict[str, Any]], upto: int) -> List[int]:
    """Index of the closest path point for each stop, walking forward so a
    line that passes a station twice (loops, a vehicle's whole day) matches
    each visit in order."""
    out: List[int] = []
    last = 0
    for s in stops[: upto + 1]:
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None or lon is None or not path:
            out.append(last)
            continue
        k = math.cos(math.radians(lat))
        best, best_d = last, float("inf")
        for i in range(last, min(len(path), last + _STOP_SEARCH_WINDOW)):
            dx = (path[i][0] - lon) * k
            dy = path[i][1] - lat
            d = dx * dx + dy * dy
            if d < best_d:
                best, best_d = i, d
            elif best_d < _NEAR_DEG2 and d > 16 * _NEAR_DEG2:
                # Matched this visit and moved on: stop before reaching the
                # same station on the way back.
                break
        out.append(best)
        last = best
    return out


def _thin(path: List[List[float]], limit: int) -> List[List[float]]:
    if len(path) <= limit:
        return path
    step = len(path) / limit
    thinned = [path[int(i * step)] for i in range(limit)]
    thinned[-1] = path[-1]
    return thinned


async def _trip_data(trip_id: str) -> Optional[Dict[str, Any]]:
    key = f"live.trip:{trip_id}"
    cached = await cache.get(key)
    if cached is not None:
        return cached
    data = await _get("/api/v1/trip", {"tripId": trip_id})
    if not isinstance(data, dict):
        return None
    legs = [leg for leg in data.get("legs") or [] if leg.get("tripId")]
    leg = next((leg for leg in legs if leg.get("tripId") == trip_id), legs[0] if legs else None)
    if not leg:
        return None
    stops = [_stop_row(s) for s in [leg.get("from") or {}, *(leg.get("intermediateStops") or []), leg.get("to") or {}]]
    stops = [s for s in stops if s["arrival"]]
    geom = leg.get("legGeometry") or {}
    word = _TRANSIT_WORDS.get(leg.get("mode") or "", "transit")
    out = {
        "trip_id": trip_id,
        "line": _line_name(leg, word),
        "mode": word,
        "headsign": leg.get("headsign"),
        "color": _color(leg.get("routeColor")) or "#4f46e5",
        "text_color": _color(leg.get("routeTextColor")),
        "agency": leg.get("agencyName"),
        "realtime": bool(leg.get("realTime")),
        "cancelled": bool(leg.get("cancelled")),
        "stops": stops,
        "path": decode_polyline(geom.get("points") or "", int(geom.get("precision") or 5)),
    }
    await cache.set(key, out, ttl=20)          # live data: refresh often
    return out


async def trip(trip_id: str, *, stop_id: Optional[str] = None, stop_name: Optional[str] = None,
               at: Optional[str] = None, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Where a trip's vehicle is and when it reaches each stop ahead.

    `vehicle` is either a moving segment (from/to stop, times, path between
    them, for the map to animate like /vehicles) or a fixed `position` while
    it waits at a stop. `your_stop` is the rider's stop (`stop_id` or
    `stop_name`; `at`, the departure they picked) with minutes until arrival."""
    data = await _trip_data(trip_id)
    if data is None:
        return None
    now = now or datetime.now(timezone.utc)
    stops = data["stops"]
    if not stops:
        return None
    times = [_parse(s["arrival"]) for s in stops]
    deps = [_parse(s["departure"]) for s in stops]
    # Next stop: the first one the vehicle hasn't left yet.
    nxt = next((i for i, d in enumerate(deps) if d and d > now), len(stops))
    finished = nxt >= len(stops)

    # A vehicle's trip can be its whole day, passing the rider's stop many
    # times; `at` (the departure the rider picked) selects the right visit.
    mine = None
    left_your_stop = False
    if stop_id or stop_name:
        # Lines at one station use different platforms (stop ids); the station name ties them.
        name = (stop_name or "").strip().lower()
        visits = [i for i in range(len(stops))
                  if (stop_id and stop_id in (stops[i]["stop_id"], stops[i]["parent_id"]))
                  or (name and stops[i]["name"].strip().lower() == name)]
        target = _parse(at) if at else None
        if target:
            near = [i for i in visits if deps[i] and abs((deps[i] - target).total_seconds()) <= 40 * 60]
            pick = min(near, key=lambda i: abs((deps[i] - target).total_seconds()), default=None)
        else:
            pick = next((i for i in visits if i >= nxt), None)
        if pick is not None and pick < nxt:
            left_your_stop = True
        elif pick is not None:
            mine = pick

    # Where this run ends: the vehicle turns back (…, A, END, A, …).
    end = next((j for j in range(max(1, nxt), len(stops) - 1) if stops[j - 1]["name"] == stops[j + 1]["name"]),
               len(stops) - 1)
    # The feed's headsign covers the vehicle's whole day; the run's last stop is where it's going now.
    headsign = stops[end]["name"]

    lo = max(0, nxt - 2)
    hi = min(end, nxt + TRIP_STOPS_AHEAD)
    if mine is not None:
        hi = max(hi, min(mine, nxt + 60))
    idx = _stop_indices(data["path"], stops, hi)
    window = []
    for i in range(lo, hi + 1):
        s = stops[i]
        window.append({**{k: v for k, v in s.items() if k != "parent_id"},
                       "passed": bool(deps[i] and deps[i] <= now) and i < nxt,
                       "minutes": None if not times[i] else max(0, round((times[i] - now).total_seconds() / 60)),
                       "yours": i == mine})

    vehicle: Optional[Dict[str, Any]] = None
    if not finished:
        here = stops[nxt]
        at_stop = times[nxt] and times[nxt] <= now        # arrived, not yet left
        if nxt == 0 or at_stop:
            vehicle = {"position": [here["lon"], here["lat"]], "at": here["name"]}
        else:
            prev = stops[nxt - 1]
            seg = data["path"][idx[nxt - 1]: idx[nxt] + 1] or [[prev["lon"], prev["lat"]], [here["lon"], here["lat"]]]
            if len(seg) < 2:
                seg = [[prev["lon"], prev["lat"]], [here["lon"], here["lat"]]]
            vehicle = {"from": prev["name"], "to": here["name"],
                       "departure": prev["departure"], "arrival": here["arrival"], "path": seg}

    path = data["path"][idx[max(0, nxt - 1)]: idx[hi] + 1] if data["path"] else []
    your_stop = None
    if mine is not None:
        s = stops[mine]
        your_stop = {"name": s["name"], "arrival": s["arrival"], "delay_min": s["delay_min"],
                     "minutes": max(0, round((times[mine] - now).total_seconds() / 60)) if times[mine] else None,
                     "stops_away": max(0, mine - nxt)}

    if finished:
        message = "This trip has finished."
    elif left_your_stop:
        message = "This vehicle has already left your stop."
    elif (stop_id or stop_name) and mine is None:
        message = "This vehicle doesn't stop at your stop in the next while."
    elif data["cancelled"]:
        message = "This trip is cancelled."
    elif not data["realtime"]:
        message = "This operator doesn't share live positions, so times and position follow the published timetable."
    else:
        message = None
    return {
        **{k: data[k] for k in ("trip_id", "line", "mode", "color", "text_color", "agency", "realtime", "cancelled")},
        "headsign": headsign,
        "stops": window,
        "vehicle": vehicle,
        "path": _thin(path, MAX_PATH_POINTS),
        "your_stop": your_stop,
        "server_time": _iso(now),
        "message": message,
    }
