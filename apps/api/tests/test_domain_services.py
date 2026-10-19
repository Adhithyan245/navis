"""Domain data services: weather, money, safety & health, transit, arrival,
local knowledge. All HTTP mocked; checks ok / partial / empty / unavailable
paths and that messages stay positive and free of provider names."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.api.services.domain import arrival as AR
from apps.api.services.domain import local_knowledge as LK
from apps.api.services.domain import money as MO
from apps.api.services.domain import safety_health as SH
from apps.api.services.domain import transit as TR
from apps.api.services.domain import weather as WE
from apps.api.services.domain.common import PlaceRef
from apps.api.services.domain.country_facts import currency_for, emergency_for

BOSTON = PlaceRef(42.36, -71.06, "Boston", "United States", "US", "Massachusetts")
TORSHAVN = PlaceRef(62.01, -6.77, "Tórshavn", "Faroe Islands", "FO")
PROVIDER_WORDS = ("geoapify", "open-meteo", "frankfurter", "groq", "wikipedia api", "traceback", "exception")


@pytest.fixture(autouse=True)
def _fresh_cache():
    from apps.api.services.cache import ttl_cache
    ttl_cache.cache._cache.clear()
    # Live feeds (alerts, bike share, Wikivoyage) are covered in test_free_apis.py.
    with patch.object(SH, "alerts_near", AsyncMock(return_value=[])), \
         patch.object(TR, "bikeshare_near", AsyncMock(return_value=None)), \
         patch.object(LK, "_travel_guide", AsyncMock(return_value=None)):
        yield


def _clean(msg: str) -> bool:
    return msg and not any(w in msg.lower() for w in PROVIDER_WORDS)


def _poi(name, d=500, **tags):
    return {"name": name, "address": "1 Main St", "categories": [], "lat": 0, "lon": 0,
            "distance_m": d, "phone": None, "website": None, "opening_hours": None, "tags": tags}


# ── weather ────────────────────────────────────────────────────────────────

OM = {"timezone": "America/New_York",
      "current": {"temperature_2m": 4.6, "apparent_temperature": 1.2, "weather_code": 61,
                  "wind_speed_10m": 40, "relative_humidity_2m": 80, "time": "2026-10-19T09:00"},
      "daily": {"time": ["2026-10-19", "2026-10-20", "2026-10-21"], "weather_code": [61, 63, 0],
                "temperature_2m_max": [9, 8, 12], "temperature_2m_min": [-1, 2, 4],
                "precipitation_probability_max": [80, 90, 10],
                "sunrise": ["06:59"] * 3, "sunset": ["17:58"] * 3}}


@pytest.mark.asyncio
async def test_weather_ok_with_packing_hints():
    with patch.object(WE, "get_json", AsyncMock(return_value=OM)):
        r = await WE.weather(BOSTON)
    assert r["status"] == "ok" and r["message"].startswith("Light rain, 5°C in Boston")
    assert len(r["data"]["days"]) == 3 and r["data"]["days"][1]["summary"] == "Rain"
    hints = " ".join(r["data"]["packing"])
    assert "Freezing nights" in hints and "Rain is likely on 2" in hints and "windy" in hints


@pytest.mark.asyncio
async def test_weather_unavailable_is_friendly():
    with patch.object(WE, "get_json", AsyncMock(return_value=None)):
        r = await WE.weather(BOSTON)
    assert r["status"] == "unavailable" and _clean(r["message"]) and r["alternatives"]


# ── money ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_money_rate():
    with patch.object(MO, "get_json", AsyncMock(return_value={"date": "2026-10-16", "rates": {"ISK": 121.03}})):
        r = await MO.money(PlaceRef(64.1, -21.9, "Reykjavik", "Iceland", "IS"), home_country_code="US")
    assert r["status"] == "ok" and r["data"]["rate"] == 121.03 and "1 USD ≈ 121.03 ISK" in r["message"]


@pytest.mark.asyncio
async def test_money_uncovered_currency_is_partial_positive():
    r = await MO.money(PlaceRef(-1.29, 36.82, "Nairobi", "Kenya", "KE"), home_country_code="US")
    assert r["status"] == "partial" and "KES" in r["message"] and _clean(r["message"])


@pytest.mark.asyncio
async def test_money_same_currency_and_unknown_country():
    same = await MO.money(BOSTON, home_country_code="US")
    assert same["status"] == "ok" and "USD" in same["message"]
    unknown = await MO.money(PlaceRef(0, 0, "Somewhere", None, "ZZ"))
    assert unknown["status"] == "empty" and unknown["alternatives"]


def test_country_facts():
    assert currency_for("fo") == "DKK" and currency_for("XX") is None
    assert emergency_for("US") == {"all": "911"} and emergency_for("DE") == {"all": "112"}
    assert emergency_for("ZZ")["unverified"] == "true"


# ── safety & health ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safety_ok():
    with patch.object(SH, "nearby", AsyncMock(return_value=[_poi("Mass General")])):
        r = await SH.safety_health(BOSTON)
    assert r["status"] == "ok" and "call 911" in r["message"] and r["data"]["hospitals"][0]["name"] == "Mass General"


@pytest.mark.asyncio
async def test_safety_lookup_failed_still_gives_numbers():
    with patch.object(SH, "nearby", AsyncMock(return_value=None)):
        r = await SH.safety_health(PlaceRef(0, 0, "Nowhere", None, "ZZ"))
    assert r["status"] == "partial" and "call 112" in r["message"] and "confirm" in r["message"]
    assert _clean(r["message"])


# ── transit ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transit_modes():
    async def fake(place, cat, **kw):
        return [_poi("Park St")] if cat.endswith(("subway", "bus")) else []
    with patch.object(TR, "nearby", side_effect=fake):
        r = await TR.transit(BOSTON, local_tip="Get a CharlieCard")
    assert r["status"] == "ok" and r["message"] == "Nearby you'll find metro, bus options."
    assert r["data"]["tip"] == "Get a CharlieCard"


@pytest.mark.asyncio
async def test_transit_none_is_positive_empty():
    with patch.object(TR, "nearby", AsyncMock(return_value=[])):
        r = await TR.transit(TORSHAVN)
    assert r["status"] == "empty" and "Walking, cycling" in r["message"]


# ── arrival ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_arrival_prefers_international_and_skips_seaplanes():
    async def fake(place, cat, **kw):
        if cat == "airport.international":
            return [_poi("Harbor Seaplane Base", 1000), _poi("Norwood Memorial Airport", 20_000, iata="OWD"),
                    _poi("Logan International Airport", 4000, iata="BOS", **{"aerodrome:type": "international"})]
        return []
    with patch.object(AR, "nearby", side_effect=fake), \
         patch.object(AR, "_timezone", AsyncMock(return_value="America/New_York")):
        r = await AR.arrival(BOSTON)
    assert r["message"] == "The nearest airport is Logan International Airport (BOS), about 4 km away."
    assert [a["name"] for a in r["data"]["airports"]] == ["Logan International Airport", "Norwood Memorial Airport"]
    assert r["data"]["timezone"] == "America/New_York" and r["data"]["local_time"]


@pytest.mark.asyncio
async def test_arrival_no_airport_is_helpful():
    with patch.object(AR, "nearby", AsyncMock(return_value=[])), \
         patch.object(AR, "_timezone", AsyncMock(return_value=None)):
        r = await AR.arrival(TORSHAVN)
    assert "no airport within 150 km" in r["message"] and _clean(r["message"])


# ── local knowledge ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_local_knowledge_combines_overview_and_culture():
    with patch.object(LK, "_overview", AsyncMock(return_value={"title": "Boston", "extract": "Boston is the capital of Massachusetts. It is old."})), \
         patch.object(LK, "_etiquette", AsyncMock(return_value={"etiquette": ["Tip 18-20%"], "phrases": [], "generated": True})):
        r = await LK.local_knowledge(BOSTON)
    assert r["status"] == "ok" and r["message"] == "Boston is the capital of Massachusetts."
    assert r["data"]["culture"]["generated"] is True


@pytest.mark.asyncio
async def test_local_knowledge_unavailable():
    with patch.object(LK, "_overview", AsyncMock(return_value=None)), \
         patch.object(LK, "_etiquette", AsyncMock(return_value=None)):
        r = await LK.local_knowledge(TORSHAVN)
    assert r["status"] == "unavailable" and _clean(r["message"]) and r["alternatives"]


@pytest.mark.asyncio
async def test_money_quotes_readable_direction():
    with patch.object(MO, "get_json", AsyncMock(return_value={"date": "2026-10-16", "rates": {"USD": 0.0113}})):
        r = await MO.money(BOSTON, home_country_code="IN")
    assert "1 USD ≈ 88.50 INR" in r["message"]
