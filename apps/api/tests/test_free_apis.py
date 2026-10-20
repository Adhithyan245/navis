"""Free public data sources: timetable transit (Transitous), live alerts
(NWS, GDACS, USGS), bike share (CityBikes), air quality (Open-Meteo),
Wikivoyage. All HTTP mocked."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from apps.api.services.domain import alerts as AL
from apps.api.services.domain import bikeshare as BK
from apps.api.services.domain import maps as MAPS
from apps.api.services.domain import weather as WE
from apps.api.services.domain.common import PlaceRef

BOSTON = PlaceRef(42.36, -71.06, "Boston", "United States", "US", "Massachusetts")
TOKYO = PlaceRef(35.68, 139.69, "Tokyo", "Japan", "JP")


@pytest.fixture(autouse=True)
def _fresh_cache():
    from apps.api.services.cache import ttl_cache
    ttl_cache.cache._cache.clear()
    yield


# ── transit ────────────────────────────────────────────────────────────────

def test_decode_polyline_precision():
    # Google's documented example, precision 5.
    assert MAPS.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5) == [
        [-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]]


def _itinerary(now: datetime):
    soon = (now + timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    later = (now + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    active = {"impactPeriod": [{"start": (now - timedelta(hours=1)).isoformat(),
                                "end": (now + timedelta(hours=1)).isoformat()}],
              "headerText": "Elevator out of service"}
    future = {"impactPeriod": [{"start": (now + timedelta(days=5)).isoformat(),
                                "end": (now + timedelta(days=6)).isoformat()}],
              "headerText": "Weekend closure"}
    return {
        "duration": 1500, "transfers": 0, "startTime": soon, "endTime": later,
        "legs": [
            {"mode": "WALK", "distance": 400, "duration": 300, "to": {"name": "State"},
             "legGeometry": {"points": "_p~iF~ps|U", "precision": 5}},
            {"mode": "SUBWAY", "duration": 600, "displayName": "Orange Line", "headsign": "Forest Hills",
             "routeColor": "ed8b00", "routeTextColor": "ffffff", "agencyName": "MBTA", "realTime": True,
             "startTime": soon, "from": {"name": "State", "tz": "America/New_York", "alerts": [active, future]},
             "to": {"name": "Downtown Crossing"}, "intermediateStops": [{}],
             "legGeometry": {"points": "_ulLnnqC", "precision": 5}},
            {"mode": "WALK", "distance": 100, "duration": 120, "to": {"name": "END"},
             "legGeometry": {"points": "", "precision": 5}},
        ],
    }


def test_itinerary_to_route_lines_alerts_steps():
    r = MAPS._itinerary_to_route(_itinerary(datetime.now(timezone.utc)))
    assert r["mode"] == "transit" and r["source"] == "timetable" and r["duration_min"] == 25.0
    assert r["lines"][0]["name"] == "Orange Line" and r["lines"][0]["color"] == "#ed8b00"
    assert r["steps"][1]["instruction"] == (
        "Take the Orange Line subway toward Forest Hills from State, 2 stops to Downtown Crossing")
    assert r["steps"][-1]["instruction"] == "Walk to your destination"
    assert r["alerts"] == ["Elevator out of service"]           # future closure not shown
    assert r["timezone"] == "America/New_York" and len(r["geometry"]) == 2


@pytest.mark.asyncio
async def test_transit_prefers_timetable_then_falls_back():
    route = {"mode": "transit", "source": "timetable"}
    with patch.object(MAPS, "_transitous", AsyncMock(return_value=route)), \
         patch.object(MAPS, "_route_one", AsyncMock(return_value={"mode": "transit"})) as est:
        assert await MAPS._transit(None, (0, 0), (1, 1)) is route
        est.assert_not_called()
    with patch.object(MAPS, "_transitous", AsyncMock(return_value=None)), \
         patch.object(MAPS, "_route_one", AsyncMock(return_value={"mode": "transit", "estimate": True})):
        assert (await MAPS._transit(None, (0, 0), (1, 1)))["estimate"]


# ── alerts ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alerts_merge_sources_and_filter_distance():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    nws = {"features": [{"properties": {"status": "Actual", "event": "Winter Storm Warning", "severity": "Severe",
                                        "headline": "Heavy snow tonight", "ends": "2026-10-20T12:00:00Z"}}]}
    gdacs = {"features": [
        {"geometry": {"coordinates": [-70.0, 42.0]}, "properties": {"eventtype": "FL", "name": "Flood in MA",
                                                                    "alertlevel": "Orange", "todate": today}},
        {"geometry": {"coordinates": [140.0, 35.0]}, "properties": {"eventtype": "TC", "name": "Far away",
                                                                    "alertlevel": "Red", "todate": today}},
    ]}
    usgs = {"features": [
        {"geometry": {"coordinates": [-71.5, 42.5]}, "properties": {"mag": 4.6, "place": "near Boston", "time": 0}},
        {"geometry": {"coordinates": [10.0, 10.0]}, "properties": {"mag": 7.0, "place": "elsewhere", "time": 0}},
    ]}

    async def fake(url, params=None, headers=None):
        return nws if "weather.gov" in url else gdacs if "gdacs" in url else usgs

    with patch.object(AL, "get_json", side_effect=fake):
        items = await AL.alerts_near(BOSTON)
    titles = [a["title"] for a in items]
    assert titles[0] == "Winter Storm Warning"
    assert "Flood in MA" in titles and "Far away" not in titles
    assert "M4.6 earthquake" in titles and len(titles) == 3


@pytest.mark.asyncio
async def test_alerts_skip_nws_outside_us_and_survive_failures():
    calls = []

    async def fake(url, params=None, headers=None):
        calls.append(url)
        return None

    with patch.object(AL, "get_json", side_effect=fake):
        assert await AL.alerts_near(TOKYO) == []      # feeds failed → no alerts, not an error
    assert not any("weather.gov" in c for c in calls)


# ── bike share ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bikeshare_picks_nearest_network_and_stations():
    nets = {"networks": [
        {"id": "far", "name": "Far Bikes", "location": {"latitude": 40.7, "longitude": -74.0, "city": "NYC"}},
        {"id": "bluebikes", "name": "Blue Bikes", "company": ["Lyft"],
         "location": {"latitude": 42.35, "longitude": -71.07, "city": "Boston"}},
    ]}
    stations = {"network": {"stations": [
        {"name": "B", "latitude": 42.40, "longitude": -71.10, "free_bikes": 1, "empty_slots": 9},
        {"name": "A", "latitude": 42.361, "longitude": -71.061, "free_bikes": 5, "empty_slots": 3},
    ]}}

    async def fake(url, params=None, headers=None):
        return stations if url.endswith("/bluebikes") else nets

    with patch.object(BK, "get_json", side_effect=fake):
        out = await BK.bikeshare_near(BOSTON)
    assert out["network"] == "Blue Bikes" and out["operator"] == "Lyft"
    assert [s["name"] for s in out["stations"]] == ["A", "B"] and out["stations"][0]["free_bikes"] == 5


@pytest.mark.asyncio
async def test_bikeshare_none_when_no_network_nearby():
    nets = {"networks": [{"id": "x", "name": "X", "location": {"latitude": 0, "longitude": 0}}]}
    with patch.object(BK, "get_json", AsyncMock(return_value=nets)):
        assert await BK.bikeshare_near(BOSTON) is None


# ── air quality ────────────────────────────────────────────────────────────

def test_aqi_labels():
    assert WE.aqi_label(20) == "Good" and WE.aqi_label(120) == "Unhealthy for sensitive groups"
    assert WE.aqi_label(None) is None


@pytest.mark.asyncio
async def test_air_quality_parses_pollen():
    payload = {"current": {"us_aqi": 160, "pm2_5": 60.1, "uv_index": 7, "grass_pollen": 12.0, "birch_pollen": None}}
    with patch.object(WE, "get_json", AsyncMock(return_value=payload)):
        air = await WE.air_quality(BOSTON)
    assert air["label"] == "Unhealthy" and air["pollen"] == {"grass": 12.0}


# ── weather fallback (MET Norway) ──────────────────────────────────────────

def test_met_symbols_map_to_wmo():
    assert WE.met_symbol_to_wmo("clearsky_day") == 0 and WE.met_symbol_to_wmo("heavyrainshowers_night") == 82
    assert WE.met_symbol_to_wmo("rainandthunder") == 95 and WE.met_symbol_to_wmo(None) is None


@pytest.mark.asyncio
async def test_weather_falls_back_to_met_norway_when_open_meteo_is_limited():
    met = {"properties": {"timeseries": [
        {"time": "2026-10-20T15:00:00Z", "data": {
            "instant": {"details": {"air_temperature": 12.0, "wind_speed": 5.0, "relative_humidity": 70}},
            "next_1_hours": {"summary": {"symbol_code": "lightrain"}, "details": {"precipitation_amount": 1.2}}}},
        {"time": "2026-10-20T18:00:00Z", "data": {
            "instant": {"details": {"air_temperature": 9.0}},
            "next_6_hours": {"summary": {"symbol_code": "cloudy"}, "details": {"precipitation_amount": 0.0}}}},
    ]}}

    async def fake(url, params=None, headers=None):
        return None if "open-meteo" in url else met

    with patch.object(WE, "get_json", side_effect=fake):
        r = await WE.weather(BOSTON)
    assert r["status"] == "ok" and r["sources"] == ["met-norway"]
    assert r["message"].startswith("Light rain, 12°C in Boston")
    day = r["data"]["days"][0]
    assert day["max_c"] == 12.0 and day["min_c"] == 9.0 and day["rain_chance"] == 70
    assert r["data"]["now"]["wind_kmh"] == 18.0
