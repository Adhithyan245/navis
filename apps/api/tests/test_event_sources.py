"""Event source adapters (Luma, Devpost, MLH, dev.events) and their merge
into EventsService. Fixtures mirror the real response shapes; no network."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from apps.api.services import events_service as ES
from apps.api.services.event_sources import base as B
from apps.api.services.event_sources import devevents, devpost, luma, mlh
from apps.api.services.event_sources.base import SourceQuery

TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
Q = SourceQuery(lat=42.36, lon=-71.06, city="Boston", region="Massachusetts", country="United States",
                country_code="US", start=TODAY, end=TODAY + timedelta(days=30))


@pytest.fixture(autouse=True)
def _fresh_cache():
    from apps.api.services.cache import ttl_cache
    ttl_cache.cache._cache.clear()
    yield


# ── Luma ───────────────────────────────────────────────────────────────────

def _luma_entry(name, day=2, calendar="Boston AI Builders", online=False, sold_out=False, lat=42.352, lon=-71.047):
    return {
        "api_id": f"evt-{name[:5]}", "calendar": {"name": calendar}, "hosts": [{"name": "Ada"}],
        "guest_count": 120, "ticket_info": {"is_free": True, "is_sold_out": sold_out, "require_approval": True},
        "waitlist_active": sold_out,
        "event": {
            "api_id": f"evt-{name[:5]}", "name": name, "url": "abc123",
            "start_at": f"{D(day)}T22:00:00.000Z", "end_at": f"{D(day)}T23:59:00.000Z",
            "timezone": "America/New_York", "cover_url": "https://images.lumacdn.com/x.png",
            "location_type": "online" if online else "offline",
            "geo_address_info": {"mode": "obfuscated", "city": "Boston", "city_state": "Boston, MA",
                                 "sublocality": "Seaport", "country": "United States",
                                 "country_code": "US", "region": "Massachusetts"},
            "coordinate": {"latitude": lat, "longitude": lon},
        },
    }


def test_luma_entry_maps_to_local_time_and_schema():
    e = luma.to_event(_luma_entry("GenAI Builders Night"), Q)
    assert e["id"] == "luma:evt-GenAI" and e["source"] == "luma" and e["category"] == "tech"
    assert e["start_time"] == "18:00:00"              # 22:00Z → 6 pm Eastern
    assert e["venue"]["city"] == "Boston" and e["distance_km"] < 3
    assert e["url"] == "https://lu.ma/abc123" and e["summary"] == "Free"
    assert e["detail"]["requires_approval"] is True and e["detail"]["hosts"] == ["Ada"]
    assert set(e) == set(B.blank_event())            # full schema present


def test_luma_non_tech_is_community_and_sold_out_is_waitlist():
    e = luma.to_event(_luma_entry("Sunday Pottery Social", calendar="Clay Club", sold_out=True), Q)
    assert e["category"] == "community" and e["status"] == "waitlist"


@pytest.mark.asyncio
async def test_luma_fetch_filters_window_and_far_away():
    entries = [_luma_entry("AI Night", 2), _luma_entry("Old AI", -10),
               _luma_entry("Far AI", 3, lat=40.7, lon=-74.0)]  # NYC, >150 km
    with patch.object(luma, "get_json", AsyncMock(return_value={"entries": entries, "has_more": False})):
        events = await luma.LumaSource().fetch(Q)
    assert [e["title"] for e in events] == ["AI Night"]


# ── Devpost ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Oct 30 - Dec 04, 2026", ("2026-10-30", "2026-12-04")),
    ("Oct 01 - 30, 2026", ("2026-10-01", "2026-10-30")),
    ("Dec 28, 2026 - Jan 03, 2027", ("2026-12-28", "2027-01-03")),
    ("Dec 28 - Jan 03, 2027", ("2026-12-28", "2027-01-03")),
    ("whenever", (None, None)),
])
def test_devpost_period(text, expected):
    assert devpost.parse_period(text) == expected


def _devpost(title, location, icon="map-marker", start=1, end=5):
    s, e = TODAY + timedelta(days=start), TODAY + timedelta(days=end)
    return {"id": hash(title) % 10_000, "title": title, "url": f"https://{title}.devpost.com",
            "displayed_location": {"icon": icon, "location": location},
            "submission_period_dates": f"{s:%b %d} - {e:%b %d, %Y}", "open_state": "open",
            "themes": [{"name": "Machine Learning/AI"}], "prize_amount": "$<span>10,000</span>",
            "thumbnail_url": "//d112y698adiu2z.cloudfront.net/x.png", "registrations_count": 300,
            "organization_name": "MIT"}


@pytest.mark.asyncio
async def test_devpost_local_country_online():
    src = devpost.DevpostSource()

    async def listing(kind, pages):
        if kind == "in-person":
            return [_devpost("hackmit", "MIT, Cambridge, Massachusetts"), _devpost("bostonhacks", "Boston University"),
                    _devpost("hack-blr", "Bengaluru, India")]
        return [_devpost("global", "Online", icon="globe")]

    with patch.object(src, "_listing", side_effect=listing):
        events = await src.fetch(Q)
    by = {e["title"]: e for e in events}
    assert set(by) == {"hackmit", "bostonhacks", "global"}
    assert by["bostonhacks"]["locality"] == "city" and by["hackmit"]["locality"] == "country"
    assert by["global"]["online"] and by["global"]["locality"] == "online"
    assert by["hackmit"]["image"].startswith("https://") and by["hackmit"]["detail"]["prizes"] == "$10,000"


# ── MLH ────────────────────────────────────────────────────────────────────

MLH_PAGE = f'''<html><body>
<a href="https://hackmit.org/?utm_source=mlh" class="block" itemScope="" itemType="https://schema.org/Event">
 <meta itemProp="url" content="https://hackmit.org/"/>
 <meta itemProp="eventAttendanceMode" content="https://schema.org/OfflineEventAttendanceMode"/>
 <meta itemProp="isAccessibleForFree" content="true"/>
 <meta itemProp="startDate" content="{D(3)}T13:00:00Z"/><meta itemProp="endDate" content="{D(4)}T20:00:00Z"/>
 <div itemProp="location"><meta itemProp="addressLocality" content="Cambridge"/>
 <meta itemProp="addressRegion" content="MA"/><meta itemProp="addressCountry" content="US"/></div>
 <h4 class="font-bold">HackMIT</h4></a>
<a href="https://x.dev" itemScope="" itemType="https://schema.org/Event">
 <meta itemProp="eventAttendanceMode" content="https://schema.org/OnlineEventAttendanceMode"/>
 <meta itemProp="startDate" content="{D(5)}T13:00:00Z"/><h4>Global Hack Week</h4></a>
<a href="https://y.dev" itemScope="" itemType="https://schema.org/Event">
 <meta itemProp="startDate" content="{D(5)}T13:00:00Z"/>
 <meta itemProp="addressLocality" content="Lleida"/><meta itemProp="addressCountry" content="ES"/><h4>LleidaHack</h4></a>
</body></html>'''


def test_mlh_parse_season():
    events = mlh.parse_season(MLH_PAGE)
    assert [e["name"] for e in events] == ["HackMIT", "Global Hack Week", "LleidaHack"]
    assert events[0]["city"] == "Cambridge" and events[0]["free"] and not events[0]["online"]
    assert events[1]["online"]


@pytest.mark.asyncio
async def test_mlh_fetch_keeps_country_and_online():
    src = mlh.MLHSource()
    with patch.object(src, "_season_events", AsyncMock(return_value=mlh.parse_season(MLH_PAGE))):
        events = await src.fetch(Q)
    assert {e["title"]: e["locality"] for e in events} == {"HackMIT": "country", "Global Hack Week": "online"}
    assert events[0]["id"].startswith("mlh:hackmit-")


# ── dev.events ─────────────────────────────────────────────────────────────

def _rss_day(n):
    return (TODAY + timedelta(days=n)).strftime("%B %d, %Y").replace(" 0", " ")


RSS = f'''<rss><channel>
<item><title><![CDATA[Boston DevOps Days]]></title><link>https://dev.events/conferences/bdd</link><guid>bdd</guid>
<description><![CDATA[Boston DevOps Days is happening on {_rss_day(6)} in Boston, United States, North America. More information: x]]></description>
<category>DevOps</category><category>conference</category></item>
<item><title><![CDATA[Clean Architecture Masterclass]]></title><link>https://dev.events/c/clean</link><guid>clean</guid>
<description><![CDATA[Clean Architecture Masterclass is happening on {_rss_day(9)}, Online. More information: x]]></description>
<category>Java</category><category>masterclass</category></item>
<item><title><![CDATA[DevFest Jaén]]></title><link>https://dev.events/c/jaen</link><guid>jaen</guid>
<description><![CDATA[DevFest Jaén is happening on {_rss_day(9)} in Jaen, Spain, Europe. More information: x]]></description></item>
</channel></rss>'''


@pytest.mark.asyncio
async def test_devevents_rss():
    items = devevents.parse_rss(RSS)
    assert [i["title"] for i in items] == ["Boston DevOps Days", "Clean Architecture Masterclass", "DevFest Jaén"]
    with patch.object(devevents, "get_text", AsyncMock(return_value=RSS)):
        events = await devevents.DevEventsSource().fetch(Q)
    by = {e["title"]: e for e in events}
    assert set(by) == {"Boston DevOps Days", "Clean Architecture Masterclass"}
    assert by["Boston DevOps Days"]["locality"] == "city" and by["Boston DevOps Days"]["subcategory"] == "conference"
    assert by["Clean Architecture Masterclass"]["online"] and by["Clean Architecture Masterclass"]["subcategory"] == "workshop"


# ── base: breaker, helpers ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_source_breaker_opens_after_failures():
    class Broken(B.EventSource):
        name = "broken"
        calls = 0

        async def fetch(self, q):
            Broken.calls += 1
            raise RuntimeError("blocked")

    src = Broken()
    for _ in range(5):
        assert await src.safe_fetch(Q) == []
    assert Broken.calls == 3  # skipped once open


@pytest.mark.parametrize("text,expected", [
    ("Boston University", "city"), ("Cambridge, Massachusetts", "country"),
    ("Austin, TX, USA", "country"), ("Bengaluru, India", None),
])
def test_place_matches(text, expected):
    assert B.place_matches(text, Q) == expected


def test_tech_detection():
    assert B.looks_tech("GenAI Builders Night") and B.looks_tech("Founders breakfast")
    assert not B.looks_tech("Sunday Pottery Social")
    assert B.tech_subcategory("HackMIT 2026 hackathon") == "hackathon"


# ── merge into EventsService ───────────────────────────────────────────────

class _Fixed(B.EventSource):
    def __init__(self, name, events):
        super().__init__()
        self.name, self._events = name, events

    async def fetch(self, q):
        return self._events


@pytest.mark.asyncio
async def test_events_service_merges_sources_dedupes_and_notes():
    luma_ev = luma.to_event(_luma_entry("AI Night", 2), Q)
    dup = dict(luma_ev, id="devev:dup", source="devevents")       # same title/date/city
    pottery = luma.to_event(_luma_entry("Pottery Social", 2, calendar="Clay"), Q)
    sources = (_Fixed("luma", [luma_ev, pottery]), _Fixed("devevents", [dup]))
    with patch.object(ES, "TECH_SOURCES", sources), \
         patch.object(ES, "_load_conferences", AsyncMock(return_value={})), \
         patch.object(ES, "_holidays_for", AsyncMock(return_value=[])), \
         patch.object(ES.settings, "TICKETMASTER_API_KEY", None):
        tech = await ES.EventsService().search(lat=42.36, lon=-71.06, city="Boston", country_code="US",
                                               category="tech", keyword="zz1" if False else None)
        community = await ES.EventsService().search(lat=42.36, lon=-71.06, city="Boston", country_code="US",
                                                    category="community")
    assert [e["title"] for e in tech["events"]] == ["AI Night"]       # dupe dropped, pottery not tech
    assert tech["sources"] == ["luma"] and tech["coverage_note"] is None
    assert [e["title"] for e in community["events"]] == ["Pottery Social"]
    detail = await ES.EventsService().detail(luma_ev["id"])
    assert detail and detail["title"] == "AI Night"


@pytest.mark.asyncio
async def test_tech_with_nothing_local_gets_positive_note():
    online = luma.to_event(_luma_entry("Remote AI", 2, online=True), Q)
    with patch.object(ES, "TECH_SOURCES", (_Fixed("luma", [online]),)), \
         patch.object(ES, "_load_conferences", AsyncMock(return_value={})), \
         patch.object(ES, "_holidays_for", AsyncMock(return_value=[])):
        out = await ES.EventsService().search(lat=62.0, lon=-6.77, city="Tórshavn", country_code="FO",
                                              category="tech")
    assert "No in-person tech events are listed in Tórshavn" in out["coverage_note"]
    assert "open to everyone" in out["coverage_note"]
