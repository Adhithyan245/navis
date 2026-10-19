"""Emergency/helpline directory, care service, map directions and the
/v2/maps + /v2/care routes. HTTP and LLM mocked."""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.services.domain import care as CARE
from apps.api.services.domain import maps as MAPS
from apps.api.services.domain.common import PlaceRef
from apps.api.services.domain.helplines import CITY, COUNTRY, directory

BOSTON = PlaceRef(42.36, -71.06, "Boston", "United States", "US", "Massachusetts")
CHENNAI = PlaceRef(13.08, 80.27, "Chennai", "India", "IN", "Tamil Nadu")
PARIS = PlaceRef(48.86, 2.35, "Paris", "France", "FR")


@pytest.fixture(autouse=True)
def _fresh_cache():
    from apps.api.services.cache import ttl_cache
    ttl_cache.cache._cache.clear()
    yield


# ── directory ──────────────────────────────────────────────────────────────

def test_boston_gets_911_and_boston_lines():
    d = directory("US", "Boston")
    assert d["primary"]["number"] == "911" and d["curated_city"]
    names = [l["name"] for l in d["city"]]
    assert "BOS:311 city services" in names and "Boston Police (non-emergency)" in names
    assert any(l["number"] == "988" for l in d["national"])


def test_chennai_gets_112_and_chennai_lines_with_alias():
    for city in ("Chennai", "madras", " CHENNAI "):
        d = directory("IN", city)
        assert d["primary"]["number"] == "112"
        assert any(l["number"] == "1913" for l in d["city"])
    assert {"100", "108", "1091", "1098"} <= {l["number"] for l in directory("IN", "Chennai")["national"]}


def test_uncurated_city_and_country_fallbacks():
    paris = directory("FR", "Paris")
    assert paris["curated_country"] and not paris["city"] and paris["primary"]["number"] == "112"
    eu = directory("NL", "Amsterdam")
    assert eu["primary"]["number"] == "112" and "EU" in eu["primary"]["note"]
    unknown = directory("ZZ", None)
    assert unknown["primary"]["number"] == "112" and not unknown["curated_country"]


def test_directory_entries_are_well_formed():
    for lines in [*COUNTRY.values(), *(l for c in CITY.values() for l in c.values())]:
        for l in lines:
            assert re.fullmatch(r"\+?[0-9]{2,15}", l["number"]), l
            assert l["category"] in {"emergency", "police", "medical", "fire", "mental_health", "women_children",
                                     "poison", "city", "utilities", "transit", "tourist", "other"}, l
    for cc, lines in COUNTRY.items():
        assert any(l["category"] == "emergency" for l in lines) or cc in {"DE", "JP", "SG", "AE"}, cc


# ── care ───────────────────────────────────────────────────────────────────

def _poi(name, **kw):
    return {"name": name, "address": "1 Main St", "categories": ["healthcare.hospital"], "lat": 1.0,
            "lon": 2.0, "distance_m": 900, "phone": "+1 617 726 2000", "website": "massgeneral.org",
            "opening_hours": "24/7", **kw}


@pytest.mark.asyncio
async def test_care_curated_city_skips_ai_and_normalizes_facilities():
    resources = AsyncMock(return_value=[{"name": "x", "url": "https://x.org"}])
    with patch.object(CARE, "nearby", AsyncMock(return_value=[_poi("MGH")])), \
         patch.object(CARE, "city_resources", resources):
        r = await CARE.care(BOSTON)
    assert r["status"] == "ok" and r["message"] == "In an emergency in Boston, call 911."
    d = r["data"]
    assert d["helplines"]["city"] and d["city_resources"] == []
    resources.assert_not_called()                      # curated city → no AI
    mgh = d["facilities"]["hospitals"]["items"][0]
    assert mgh["website"] == "https://massgeneral.org" and mgh["phone"]
    assert [b["name"] for b in d["booking"]][:1] == ["Zocdoc"]


@pytest.mark.asyncio
async def test_care_uncurated_city_gets_link_checked_sites_not_numbers():
    sites = [{"name": "Mairie de Paris", "url": "https://www.paris.fr", "category": "city", "generated": True}]
    with patch.object(CARE, "nearby", AsyncMock(return_value=[])), \
         patch.object(CARE, "city_resources", AsyncMock(return_value=sites)):
        r = await CARE.care(PARIS)
    d = r["data"]
    assert d["helplines"]["city"] == [] and d["city_resources"] == sites
    assert r["status"] == "partial" and r["alternatives"]          # nothing mapped nearby
    assert d["booking"][0]["name"] == "Doctolib"


@pytest.mark.asyncio
async def test_city_resources_keeps_only_live_links():
    llm = {"choices": [{"message": {"content": '{"sites": [{"name": "A", "url": "https://good.example", "category": "city"},'
                                               '{"name": "B", "url": "https://dead.example", "category": "city"},'
                                               '{"name": "C", "url": "ftp://bad", "category": "city"}]}'}}]}

    class Resp:
        status = 200
        async def json(self):
            return llm
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    class Session:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def post(self, *a, **k):
            return Resp()

    async def link_ok(session, url):
        return "good" in url

    with patch.object(CARE.settings, "GROQ_API_KEY", "k"), \
         patch.object(CARE.aiohttp, "ClientSession", Session), \
         patch.object(CARE, "_link_ok", side_effect=link_ok):
        sites = await CARE.city_resources(PARIS)
    assert [s["url"] for s in sites] == ["https://good.example"] and sites[0]["generated"]


# ── maps ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_directions_reports_missing_transit_positively():
    async def one(session, origin, dest, mode):
        if mode == "transit":
            return None
        return {"mode": mode, "distance_km": 2.8, "duration_min": 5.0, "geometry": [[0, 0], [1, 1]], "steps": []}
    with patch.object(MAPS, "_route_one", side_effect=one), patch.object(MAPS.settings, "GEOAPIFY_API_KEY", "k"), \
         patch.object(MAPS, "_transitous", AsyncMock(return_value=None)):
        out = await MAPS.directions((42.36, -71.05), (42.36, -71.08), ["drive", "walk", "transit"])
    assert [r["mode"] for r in out["routes"]] == ["drive", "walk"]
    assert "transit directions aren't available" in out["message"]


def test_flatten_multiline():
    assert MAPS._flatten({"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[2, 2]]]}) == [[0, 0], [1, 1], [2, 2]]


@pytest.mark.asyncio
async def test_places_by_category_messages():
    with patch.object(MAPS, "nearby", AsyncMock(return_value=[])):
        r = await MAPS.places_by_category(BOSTON, "pharmacies", radius_m=3000)
    assert r["items"] == [] and "No pharmacies are mapped within 3 km" in r["message"]
    with patch.object(MAPS, "nearby", AsyncMock(return_value=None)):
        r = await MAPS.places_by_category(BOSTON, "pharmacies")
    assert "aren't loading" in r["message"]


# ── routes ─────────────────────────────────────────────────────────────────

def _client():
    from apps.api.main import app
    return TestClient(app)


def test_map_routes_validate_and_delegate():
    from apps.api.routes import maps as R
    c = _client()
    assert c.get("/v2/maps/nearby", params={"lat": 1, "lon": 1, "category": "bogus"}).status_code == 422
    assert len(c.get("/v2/maps/categories").json()["categories"]) == len(MAPS.CATEGORIES)
    with patch.object(R, "directions", AsyncMock(return_value={"routes": [], "message": None})) as d:
        c.get("/v2/maps/route", params={"from_lat": 1, "from_lon": 2, "to_lat": 3, "to_lon": 4, "modes": "drive,teleport"})
    assert d.call_args.args[2] == ["drive"]


def test_care_route_reverse_geocodes_missing_place_info():
    from apps.api.routes import maps as R

    class Loc:
        country_code, country, city, name, region = "IN", "India", "Chennai", "Chennai", "Tamil Nadu"

    seen = {}

    async def fake_care(place):
        seen["place"] = place
        return {"status": "ok"}

    with patch.object(R.geocoding_service, "reverse", AsyncMock(return_value=Loc())), \
         patch.object(R, "care", fake_care):
        r = _client().get("/v2/care", params={"lat": 13.08, "lon": 80.27})
    assert r.status_code == 200 and seen["place"].city == "Chennai" and seen["place"].country_code == "IN"


# ── place details ──────────────────────────────────────────────────────────

def test_name_score():
    assert MAPS._name_score("Trader Joe's", "Trader Joe's") == 1
    assert MAPS._name_score("Boston Common", "Found Hotel Boston Common") < 0.6


@pytest.mark.asyncio
async def test_place_details_prefers_osm_match_and_adds_wiki():
    osm = {"name": "Old State House", "address": "208 Washington Street", "categories": ["tourism", "tourism.museum"],
           "lat": 42.3588, "lon": -71.0574, "phone": None, "website": "https://revolutionaryspaces.org/",
           "opening_hours": "Mo-Su 10:00-17:00", "attributes": {}, "landmark": True,
           "_wikipedia": None, "_wikidata": "Q1320533"}
    wiki = AsyncMock(return_value={"extract": "A historic building.", "image": "https://img", "url": "https://w"})
    geo = AsyncMock(return_value=None)
    with patch.object(MAPS, "_nominatim", AsyncMock(return_value=dict(osm))), \
         patch.object(MAPS, "_geoapify_poi", geo), \
         patch.object(MAPS, "_enwiki_from_wikidata", AsyncMock(return_value="en:Old State House (Boston)")), \
         patch.object(MAPS, "_wiki", wiki):
        p = (await MAPS.place_details(42.3588, -71.0574, "Old State House"))["place"]
    geo.assert_not_called()
    assert p["opening_hours"] and p["about"]["extract"] and "_wikidata" not in p and "_wikipedia" not in p
    assert wiki.call_args.args[1] == "en:Old State House (Boston)"


@pytest.mark.asyncio
async def test_place_details_falls_back_to_bare_pin():
    with patch.object(MAPS, "_nominatim", AsyncMock(return_value=None)), \
         patch.object(MAPS, "_geoapify_poi", AsyncMock(return_value=None)), \
         patch.object(MAPS.settings, "GEOAPIFY_API_KEY", "k"):
        out = await MAPS.place_details(1.0, 2.0, "Corner Shop")
    assert out == {"place": {"name": "Corner Shop", "lat": 1.0, "lon": 2.0}}


def test_place_route_delegates():
    from apps.api.routes import maps as R
    with patch.object(R, "place_details", AsyncMock(return_value={"place": {"name": "X"}})) as pd:
        r = _client().get("/v2/maps/place", params={"lat": 1, "lon": 2, "name": "  X "})
    assert r.status_code == 200 and pd.call_args.args == (1.0, 2.0, "X")
