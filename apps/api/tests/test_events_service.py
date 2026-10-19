"""EventsService normalization, filtering and fallbacks (sources mocked)."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from apps.api.services import events_service as ES
from apps.api.services.place_extraction import find_place, is_activity_query

TODAY = date.today()


@pytest.fixture(autouse=True)
def _no_external_sources():
    """Luma/Devpost/MLH/dev.events have their own tests; keep these offline."""
    with patch.object(ES, "TECH_SOURCES", ()):
        yield
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731


def _tm_raw(i=1, segment="Music", genre="Rock", family=False, status="onsale", day=1):
    return {
        "id": f"ev{i}", "name": f"Show {i}", "url": f"https://tm/{i}",
        "dates": {"start": {"localDate": D(day), "localTime": "20:00:00", "dateTime": "x"},
                  "timezone": "America/New_York", "status": {"code": status}},
        "classifications": [{"segment": {"name": segment}, "genre": {"name": genre}, "family": family}],
        "priceRanges": [{"min": 25.0, "max": 80.0, "currency": "USD"}],
        "images": [{"ratio": "16_9", "width": 640, "url": "https://img/640"},
                   {"ratio": "16_9", "width": 2048, "url": "https://img/2048"}],
        "_embedded": {"venues": [{
            "name": "Hall", "address": {"line1": "1 Main St"}, "city": {"name": "Boston"},
            "state": {"stateCode": "MA"}, "country": {"name": "United States", "countryCode": "US"},
            "postalCode": "02114", "location": {"latitude": "42.366", "longitude": "-71.06"},
        }]},
    }


def test_tm_event_normalized():
    e = ES._tm_event(_tm_raw(), (42.36, -71.06))
    assert e["id"] == "tm:ev1" and e["category"] == "music" and e["subcategory"] == "Rock"
    assert e["start_time"] == "20:00:00" and e["timezone"] == "America/New_York"
    assert e["price"] == {"min": 25.0, "max": 80.0, "currency": "USD"}
    assert e["venue"]["address"] == "1 Main St, Boston, MA, 02114"
    assert e["image"] == "https://img/640"
    assert e["distance_km"] is not None and e["distance_km"] < 2


@pytest.mark.parametrize("segment,genre,family,expected", [
    ("Arts & Theatre", "Comedy", False, "comedy"),
    ("Arts & Theatre", "Theatre", True, "family"),
    ("Sports", "Hockey", True, "sports"),
    ("Miscellaneous", "Undefined", False, "community"),
    ("Film", "Drama", False, "film"),
])
def test_tm_categories(segment, genre, family, expected):
    e = ES._tm_event(_tm_raw(segment=segment, genre=genre, family=family), None)
    assert e["category"] == expected


def _conf(name, city, country, online=False, start=1, end=1):
    return {"name": name, "url": f"https://{name}", "startDate": D(start), "endDate": D(end),
            "city": city, "country": country, "online": online, "topics": ["python"]}


@pytest.mark.asyncio
async def test_conferences_locality_and_country_aliases():
    index = {}
    for c in [_conf("LocalConf", "Boston, MA", "U.S.A."), _conf("UsConf", "Austin, TX", "U.S.A."),
              _conf("OnlineConf", None, None, online=True), _conf("FarConf", "Berlin", "Germany")]:
        index[ES._conf_id(c)] = c
    with patch.object(ES, "_load_conferences", AsyncMock(return_value=index)):
        local = await ES._conferences(city="Boston", country_code="US", country="United States",
                                      start=TODAY, end=TODAY + timedelta(days=30), keyword=None,
                                      include_elsewhere=False)
        everywhere = await ES._conferences(city="Boston", country_code="US", country="United States",
                                           start=TODAY, end=TODAY + timedelta(days=30), keyword=None,
                                           include_elsewhere=True)
    assert [e["title"] for e in local] == ["LocalConf", "UsConf", "OnlineConf"]
    assert [e["locality"] for e in local] == ["city", "country", "online"]
    assert "FarConf" in [e["title"] for e in everywhere]


def test_hybrid_conference_is_not_marked_online_only():
    e = ES._conf_event(_conf("Hybrid", "Potsdam", "Germany", online=True), local="online")
    assert e["hybrid"] is True and e["online"] is False


@pytest.mark.asyncio
async def test_search_widens_radius_and_explains_coverage():
    calls = []

    async def fake_get(session, url, params=None):
        if "ticketmaster" in url:
            calls.append(params["radius"])
            n = 2 if params["radius"] < 300 else 9
            return 200, {"_embedded": {"events": [_tm_raw(i) for i in range(n)]}}
        return 200, []

    svc = ES.EventsService()
    with patch.object(ES, "_get_json", fake_get), \
         patch.object(ES, "_load_conferences", AsyncMock(return_value={})), \
         patch.object(ES, "_holidays_for", AsyncMock(return_value=[])), \
         patch.object(ES.settings, "TICKETMASTER_API_KEY", "k"):
        out = await svc.search(lat=10.0, lon=10.0, city="Smalltown", country_code="US",
                               category="music", keyword="zz-unique-1")
    assert calls == [25, 100, 300]
    assert out["radius_km"] == 300 and len(out["events"]) == 9
    assert "300 km" in out["coverage_note"]


@pytest.mark.asyncio
async def test_no_ticketed_coverage_still_returns_holidays_and_note():
    holiday = {"date": D(2), "localName": "Þjóðhátíðardagurinn", "name": "National Day",
               "countryCode": "IS", "global": True, "types": ["Public"]}

    async def empty(session, url, params=None):
        return 200, {}

    svc = ES.EventsService()
    with patch.object(ES, "_get_json", empty), \
         patch.object(ES, "_load_conferences", AsyncMock(return_value={})), \
         patch.object(ES, "_holidays_for", AsyncMock(return_value=[holiday])), \
         patch.object(ES.settings, "TICKETMASTER_API_KEY", "k"):
        out = await svc.search(lat=64.1, lon=-21.9, city="Reykjavik", country_code="IS",
                               keyword=None, date_from=D(0), date_to=D(7))
    assert [e["category"] for e in out["events"]] == ["holiday"]
    assert out["events"][0]["title"] == "National Day (Þjóðhátíðardagurinn)"
    assert "Local listings for Reykjavik are thin" in out["coverage_note"]


@pytest.mark.asyncio
async def test_holiday_detail_roundtrip():
    h = {"date": D(3), "localName": "X", "name": "Y Day", "countryCode": "IS", "global": True, "types": ["Public"]}
    with patch.object(ES, "_holidays_for", AsyncMock(return_value=[h])):
        ev = await ES.EventsService().detail(ES._holiday_id(h))
    assert ev and ev["title"] == "Y Day (X)" and ev["detail"]["local_name"] == "X"


@pytest.mark.asyncio
async def test_unknown_detail_id_is_none():
    assert await ES.EventsService().detail("nope:123") is None


def test_events_route_validates_category():
    from fastapi.testclient import TestClient
    from apps.api.main import app
    r = TestClient(app).get("/v2/events", params={"lat": 1, "lon": 1, "category": "bogus"})
    assert r.status_code == 422


# ── place anchoring ────────────────────────────────────────────────────────

@pytest.mark.parametrize("q,place,activity", [
    ("good brunch spots", None, True),
    ("things to do", None, True),
    ("pharmacy near me", None, True),
    ("where can I buy a SIM card", None, False),
    ("AI startup events and coworking spaces", None, True),  # not Anguilla
    ("best cafes in Lisbon", "Lisbon", False),
    ("Hobart", "Hobart", False),
])
def test_find_place_and_activity(q, place, activity):
    assert find_place(q) == place
    assert is_activity_query(q) is activity


@pytest.mark.asyncio
async def test_geo_provider_anchors_activity_query_on_city():
    from apps.api.services.providers.geo import GeoProvider
    gp = GeoProvider()
    lookups = []

    async def lookup(text):
        lookups.append(text)
        return {"lat": "64.14", "lon": "-21.94", "name": text} if text == "Reykjavik" else None

    with patch.object(gp, "_lookup", side_effect=lookup):
        fetch = GeoProvider.fetch.__wrapped__.__wrapped__  # skip cache + breaker
        hit = await fetch(gp, "good brunch spots", city="Reykjavik")
    assert hit["name"] == "Reykjavik" and lookups[0] == "Reykjavik"


@pytest.mark.asyncio
async def test_geo_provider_falls_back_to_trailing_place_name():
    from apps.api.services.providers.geo import GeoProvider
    gp = GeoProvider()

    async def lookup(text):
        return {"lat": "64.1", "lon": "-21.9", "name": text} if text == "Reykjavik" else None

    with patch.object(gp, "_lookup", side_effect=lookup), \
         patch.object(gp, "_service_lookup", AsyncMock(return_value=None)):
        fetch = GeoProvider.fetch.__wrapped__.__wrapped__
        hit = await fetch(gp, "coffee near Old Harbour Reykjavik", city=None)
    assert hit["name"] == "Reykjavik"
