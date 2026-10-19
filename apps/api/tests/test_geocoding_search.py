"""Location search: address normalization, local bias, aliases, acronyms.

Providers are mocked; these tests pin the ranking/merging logic in
GeocodingService._forward and the helpers in services/geocode_query.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.api.models.location import Location
from apps.api.services import geocode_query as gq
from apps.api.services import geocoding as G
from apps.api.services.geocode_query import looks_like_acronym, normalize_query

BOSTON = (42.36, -71.06)


def _loc(name, lat, lon, *, provider="geoapify", type_="landmark", conf=1.0,
         label=None, aliases=None) -> Location:
    raw = {"namedetails": aliases} if aliases else {}
    return Location(id=f"{provider}:{name}:{lat}", type=type_, name=name,
                    label=label or name, lat=lat, lon=lon, provider=provider,
                    confidence=conf, raw=raw)


# ── normalize_query ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Kendall Sq", "Kendall Square"),
    ("Back Bay Stn", "Back Bay Station"),
    ("Fenway Pk", "Fenway Park"),
    ("12 Westland Ave Apt 3", "12 Westland Avenue"),
    ("360 Huntington Ave #405, Boston", "360 Huntington Avenue, Boston"),
    ("1 Comm Ave, Unit 4", "1 Comm Avenue"),
    ("Elm St, Floor 2", "Elm Street"),
    ("St Louis", "Saint Louis"),
    ("Mt Auburn St", "Mount Auburn Street"),
    ("Ste-Foy", "Ste-Foy"),
    ("Chennai", "Chennai"),
])
def test_normalize_query(raw, expected):
    assert normalize_query(raw) == expected


@pytest.mark.parametrize("text,expected", [
    ("MIT", True), ("NEU", True), ("JP", True), ("NYC", True), ("bu", True),
    ("Boston", False), ("Hunting", False), ("12 Main", False), ("Back Bay", False),
])
def test_looks_like_acronym(text, expected):
    assert looks_like_acronym(text) is expected


@pytest.mark.asyncio
async def test_expand_acronym_without_key_returns_none():
    with patch.object(gq.settings, "GROQ_API_KEY", None):
        assert await gq.expand_acronym("NEU", "Boston") is None


# ── ranking + merging ──────────────────────────────────────────────────────

def _service(geo=None, nom=None):
    svc = G.GeocodingService()
    svc._geoapify_forward = AsyncMock(side_effect=geo or (lambda *a, **k: []))
    svc._nominatim_forward = AsyncMock(side_effect=nom or (lambda *a, **k: []))
    return svc


async def _geo(results_by_query):
    async def fake(text, **kwargs):
        return list(results_by_query.get(text, []))
    return fake


@pytest.mark.asyncio
async def test_bias_ranks_local_address_first():
    far = _loc("12 Westland Avenue", 42.46, -71.14, type_="address", label="12 Westland Avenue, Winchester")
    near = _loc("12 Westland Avenue", 42.344, -71.088, type_="address", label="12 Westland Avenue, Boston")
    svc = _service(geo=await _geo({"12 Westland Avenue": [far, near]}))
    out = await svc._forward("12 Westland Ave Apt 3", limit=3, autocomplete=False, bias=BOSTON)
    assert out[0].label.endswith("Boston")
    # The apartment number was stripped before calling the provider.
    assert svc._geoapify_forward.call_args.args[0] == "12 Westland Avenue"


@pytest.mark.asyncio
async def test_without_bias_far_results_still_returned():
    far = _loc("Cambridge", 52.2, 0.12, type_="city")
    svc = _service(geo=await _geo({"Cambridge": [far]}))
    out = await svc._forward("Cambridge", limit=3, autocomplete=False, bias=None)
    assert [o.name for o in out] == ["Cambridge"]


@pytest.mark.asyncio
async def test_osm_alias_beats_business_named_like_the_query():
    gas = _loc("Southie Gas", 42.335, -71.05)
    far = _loc("Southie", 37.77, -122.27)
    south_boston = _loc("South Boston", 42.333, -71.048, provider="nominatim",
                        type_="suburb", conf=0.44, aliases={"alt_name": "Southie"})
    svc = _service(geo=await _geo({"Southie": [gas, far]}),
                   nom=await _geo({"Southie": [south_boston]}))
    out = await svc._forward("Southie", limit=3, autocomplete=False, bias=BOSTON)
    assert out[0].name == "South Boston"
    svc._nominatim_forward.assert_awaited()  # far exact match didn't suppress OSM


@pytest.mark.asyncio
async def test_acronym_expansion_is_shown_first():
    literal = _loc("Neu-Ulm", 48.39, 10.0, type_="county")
    nu = _loc("Northeastern University", 42.339, -71.088)
    svc = _service(geo=await _geo({"NEU": [literal],
                                   "Northeastern University, Boston": [nu]}))
    with patch.object(G, "expand_acronym", AsyncMock(return_value="Northeastern University, Boston")):
        out = await svc._forward("NEU", limit=3, autocomplete=False, bias=BOSTON, city="Boston")
    assert out[0].name == "Northeastern University"
    assert "expanded" in out[0].tags


@pytest.mark.asyncio
async def test_same_place_from_two_providers_is_merged():
    a = _loc("Massachusetts Institute of Technology", 42.3601, -71.0942)
    b = _loc("Massachusetts Institute of Technology", 42.3591, -71.0920, provider="nominatim", conf=0.7)
    svc = _service(geo=await _geo({"MIT": [a]}), nom=await _geo({"MIT": [b]}))
    with patch.object(G, "expand_acronym", AsyncMock(return_value=None)):
        out = await svc._forward("MIT", limit=5, autocomplete=False, bias=BOSTON)
    assert [o.name for o in out].count("Massachusetts Institute of Technology") == 1


@pytest.mark.asyncio
async def test_misses_are_not_cached():
    svc = _service()
    assert await svc.search("zzqx nowhere", limit=3) == []
    hit = _loc("Zzqx Plaza", 1.0, 1.0)
    svc._geoapify_forward = AsyncMock(return_value=[hit])
    out = await svc.search("zzqx nowhere", limit=3)
    assert [o.name for o in out] == ["Zzqx Plaza"]


@pytest.mark.asyncio
async def test_nominatim_skipped_while_another_call_waits():
    from apps.api.core import throttle
    await throttle._lock.acquire()
    try:
        with pytest.raises(G._NominatimBusy):
            await G._nominatim_throttle()
    finally:
        throttle._lock.release()


def test_geocode_route_accepts_bias_params():
    from fastapi.testclient import TestClient
    from apps.api.main import app
    from apps.api.routes import geocode

    mock = AsyncMock(return_value=[])
    with patch.object(geocode.geocoding_service, "search", mock):
        r = TestClient(app).get("/v2/geocode/search", params={
            "text": "NEU", "autocomplete": "true",
            "bias_lat": 42.36, "bias_lon": -71.06, "city": "Boston"})
    assert r.status_code == 200
    kwargs = mock.call_args.kwargs
    assert kwargs["bias_lat"] == 42.36 and kwargs["bias_lon"] == -71.06
    assert kwargs["city"] == "Boston"
