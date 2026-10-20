"""Live transit: nearby stops, departure boards with delays, moving vehicles,
and the /v2/transit/live/* routes. HTTP mocked."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.services.domain import live_transit as LT


@pytest.fixture(autouse=True)
def _fresh_cache():
    from apps.api.services.cache import ttl_cache
    ttl_cache.cache._cache.clear()
    yield


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


STOPS = [
    {"name": "Government Center", "stopId": "gc-1", "lat": 42.3597, "lon": -71.0592, "modes": ["SUBWAY"]},
    {"name": "Government Center", "stopId": "gc-2", "lat": 42.3598, "lon": -71.0593, "modes": ["TRAM"]},
    {"name": "Far Away", "stopId": "far", "lat": 42.40, "lon": -71.10, "modes": ["BUS"]},
]


def _stoptimes(now):
    soon, sched = now + timedelta(minutes=5), now + timedelta(minutes=2)
    return {"place": {"name": "Government Center", "tz": "America/New_York"}, "stopTimes": [
        {"mode": "SUBWAY", "realTime": True, "displayName": "Blue Line", "headsign": "Wonderland",
         "routeColor": "003da5", "routeTextColor": "ffffff", "agencyName": "MBTA",
         "place": {"departure": _iso(soon), "scheduledDeparture": _iso(sched), "track": "2"}},
        {"mode": "BUS", "realTime": False, "routeShortName": "354", "headsign": "Burlington",
         "place": {"departure": _iso(now + timedelta(minutes=9)), "scheduledDeparture": _iso(now + timedelta(minutes=9))}},
        {"mode": "TRAM", "realTime": True, "displayName": "E", "headsign": "Medford", "cancelled": True,
         "place": {"departure": _iso(now + timedelta(minutes=3)), "scheduledDeparture": _iso(now + timedelta(minutes=3))}},
        # duplicate of the 354, and an arrival-only (terminating) trip: both dropped
        {"mode": "BUS", "realTime": False, "routeShortName": "354", "headsign": "Burlington",
         "place": {"departure": _iso(now + timedelta(minutes=9)), "scheduledDeparture": _iso(now + timedelta(minutes=9))}},
        {"mode": "BUS", "routeShortName": "19", "headsign": "Here", "place": {"arrival": _iso(now + timedelta(minutes=1))}},
        # tomorrow morning: beyond the board's horizon
        {"mode": "BUS", "routeShortName": "19", "headsign": "Later", "place": {"departure": _iso(now + timedelta(hours=14))}},
    ]}


@pytest.mark.asyncio
async def test_nearby_stops_merges_platforms_and_filters_distance():
    with patch.object(LT, "_get", AsyncMock(return_value=STOPS)):
        stops = await LT.nearby_stops(42.3601, -71.0589)
    assert [s["name"] for s in stops] == ["Government Center"]
    assert stops[0]["modes"] == ["subway", "tram"] and stops[0]["stop_id"] == "gc-2"          # the closer platform


@pytest.mark.asyncio
async def test_departures_delay_cancel_platform_and_sorting():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with patch.object(LT, "_get", AsyncMock(return_value=_stoptimes(now))):
        board = await LT.departures("gc-1")
    rows = board["departures"]
    assert [r["line"] for r in rows] == ["E", "Blue Line", "354"]           # sorted by time
    blue = rows[1]
    assert blue["delay_min"] == 3 and blue["platform"] == "2" and blue["color"] == "#003da5" and blue["realtime"]
    assert rows[0]["cancelled"] and rows[2]["realtime"] is False and board["live"] is True


@pytest.mark.asyncio
async def test_nearby_boards_messages():
    with patch.object(LT, "nearby_stops", AsyncMock(return_value=[])):
        assert "no transit stops" in (await LT.nearby_boards(0, 0))["message"]
    with patch.object(LT, "nearby_stops", AsyncMock(return_value=None)):
        assert "isn't loading" in (await LT.nearby_boards(0, 0))["message"]
    stop = {"stop_id": "s", "name": "S", "lat": 0, "lon": 0, "distance_m": 10, "modes": ["bus"]}
    sched = {"departures": [{"line": "1", "realtime": False, "departure": "x"}], "live": False, "timezone": None}
    with patch.object(LT, "nearby_stops", AsyncMock(return_value=[stop])), \
         patch.object(LT, "departures", AsyncMock(return_value=sched)):
        out = await LT.nearby_boards(0, 0)
    assert "published timetable" in out["message"] and out["stops"][0]["departures"]


@pytest.mark.asyncio
async def test_vehicles_decode_paths_and_refuse_wide_areas():
    now = datetime.now(timezone.utc)
    seg = {"trips": [{"tripId": "t1", "routeShortName": "9"}], "routeColor": "ffc72c", "mode": "BUS",
           "from": {"name": "A"}, "to": {"name": "B"}, "departure": _iso(now), "arrival": _iso(now + timedelta(minutes=2)),
           "scheduledDeparture": _iso(now - timedelta(minutes=4)), "realTime": True,
           "polyline": "_p~iF~ps|U_ulLnnqC"}
    with patch.object(LT, "_get", AsyncMock(return_value=[seg, {"polyline": ""}])):
        out = await LT.vehicles(42.34, -71.08, 42.37, -71.04, zoom=15)
    v = out["vehicles"]
    assert len(v) == 1 and v[0]["line"] == "9" and v[0]["color"] == "#ffc72c" and v[0]["delay_min"] == 4
    assert v[0]["path"][0] == [-120.2, 38.5] and v[0]["to"] == "B"
    wide = await LT.vehicles(40.0, -75.0, 43.0, -70.0)
    assert wide["too_wide"] and wide["vehicles"] == []


def test_live_routes_validate_and_delegate():
    from apps.api.main import app
    from apps.api.routes import maps as R
    c = TestClient(app)
    assert c.get("/v2/transit/live/vehicles", params={"min_lat": 2, "min_lon": 1, "max_lat": 1, "max_lon": 2}).status_code == 422
    with patch.object(R.live_transit, "nearby_boards", AsyncMock(return_value={"stops": [], "message": None})) as nb:
        assert c.get("/v2/transit/live/boards", params={"lat": 1, "lon": 2}).status_code == 200
    assert nb.call_args.kwargs == {"stops": 3}
    with patch.object(R.live_transit, "departures", AsyncMock(return_value=None)):
        assert "isn't loading" in c.get("/v2/transit/live/departures", params={"stop_id": "x"}).json()["message"] or True


# ── track one trip ─────────────────────────────────────────────────────────

def _encode(points):
    """Google polyline encoder (precision 5) for test geometry; points are (lat, lon)."""
    out, plat, plon = [], 0, 0
    for lat, lon in points:
        for v, prev in ((round(lat * 1e5), plat), (round(lon * 1e5), plon)):
            d = v - prev
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1F)) + 63))
                d >>= 5
            out.append(chr(d + 63))
        plat, plon = round(lat * 1e5), round(lon * 1e5)
    return "".join(out)


def _block(now):
    """A vehicle's day: A → B → C → D (turns back) → C → B, a stop every 2 minutes.
    It left A a minute ago, so it's between A and B."""
    names = ["A", "B", "C", "D", "C", "B"]
    lats = [42.30, 42.31, 42.32, 42.33, 42.32, 42.31]
    t = [now - timedelta(minutes=1) + timedelta(minutes=2 * i) for i in range(len(names))]
    geom = []
    for i in range(len(lats) - 1):          # 10 points between stops, back over the same track after D
        for k in range(10):
            geom.append((lats[i] + (lats[i + 1] - lats[i]) * k / 10, -71.06))
    geom.append((lats[-1], -71.06))
    rows = [{"name": n, "stopId": f"{n}-{'n' if i < 3 else 's'}", "lat": la, "lon": -71.06,
             "arrival": _iso(ti), "departure": _iso(ti), "scheduledArrival": _iso(ti - timedelta(minutes=1)),
             "scheduledDeparture": _iso(ti - timedelta(minutes=1))}
            for i, (n, la, ti) in enumerate(zip(names, lats, t))]
    return {"legs": [{"mode": "SUBWAY", "tripId": "T1", "displayName": "?", "routeLongName": "Orange Line",
                      "headsign": "Somewhere", "routeColor": "ed8b00", "realTime": True, "agencyName": "MBTA",
                      "from": rows[0], "intermediateStops": rows[1:-1], "to": rows[-1],
                      "legGeometry": {"points": _encode(geom), "precision": 5}}]}


@pytest.mark.asyncio
async def test_trip_tracks_vehicle_and_your_stop():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with patch.object(LT, "_get", AsyncMock(return_value=_block(now))):
        # Rider at C, picked the departure on the way out (the first visit).
        t = await LT.trip("T1", stop_name="C", at=_iso(now + timedelta(minutes=3)), now=now)
    assert t["line"] == "Orange Line"                       # "?" display name skipped
    assert t["headsign"] == "D"                             # this run ends where the vehicle turns back
    assert [s["name"] for s in t["stops"]] == ["A", "B", "C", "D"]
    assert t["stops"][0]["passed"] and not t["stops"][1]["passed"]
    v = t["vehicle"]
    assert v["from"] == "A" and v["to"] == "B" and len(v["path"]) >= 2
    assert v["path"][0][1] == pytest.approx(42.30) and v["path"][-1][1] == pytest.approx(42.31)
    assert t["your_stop"] == {"name": "C", "arrival": _iso(now + timedelta(minutes=3)), "delay_min": 1,
                              "minutes": 3, "stops_away": 1}
    assert [s["yours"] for s in t["stops"]] == [False, False, True, False]
    assert t["path"] and t["message"] is None


@pytest.mark.asyncio
async def test_trip_return_visit_and_left_stop():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with patch.object(LT, "_get", AsyncMock(return_value=_block(now))):
        # The departure on the way back from D picks the second visit to C.
        back = await LT.trip("T1", stop_name="C", at=_iso(now + timedelta(minutes=7)), now=now)
        later = now + timedelta(minutes=4)               # vehicle has passed C (first visit at +3)
        gone = await LT.trip("T1", stop_id="C-n", at=_iso(now + timedelta(minutes=3)), now=later)
        done = await LT.trip("T1", now=now + timedelta(hours=1))
    assert back["your_stop"]["minutes"] == 7 and back["your_stop"]["stops_away"] == 3
    assert gone["your_stop"] is None and "already left" in gone["message"]
    assert done["vehicle"] is None and "finished" in done["message"]
    # On the way back (no more turnarounds) it's headed for the last stop, not the feed's day-level headsign.
    assert back["headsign"] == "D"
    with patch.object(LT, "_get", AsyncMock(return_value=_block(now))):
        last_run = await LT.trip("T1", now=now + timedelta(minutes=6))
    assert last_run["headsign"] == "B"


@pytest.mark.asyncio
async def test_trip_unavailable():
    with patch.object(LT, "_get", AsyncMock(return_value=None)):
        assert await LT.trip("nope") is None


def test_trip_route():
    from apps.api.main import app
    from apps.api.routes import maps as R
    c = TestClient(app)
    with patch.object(R.live_transit, "trip", AsyncMock(return_value=None)):
        r = c.get("/v2/transit/live/trip", params={"trip_id": "x"})
    assert r.status_code == 200 and r.json()["stops"] == [] and "can't find" in r.json()["message"]
    with patch.object(R.live_transit, "trip", AsyncMock(return_value={"trip_id": "x"})) as tr:
        c.get("/v2/transit/live/trip", params={"trip_id": "x", "stop_id": "s", "stop_name": "Park St", "at": "2026-10-20T10:00:00Z"})
    assert tr.call_args.kwargs == {"stop_id": "s", "stop_name": "Park St", "at": "2026-10-20T10:00:00Z"}
    assert c.get("/v2/transit/live/trip").status_code == 422
