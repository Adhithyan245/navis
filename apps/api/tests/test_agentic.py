"""Multi-agent layer: routing, supervisor streaming, failure isolation,
positive empty states, metrics/breaker, catalog routes. No network."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, patch

import orjson
import pytest

from apps.api.agentic import metrics, supervisor
from apps.api.agentic.base import AgentResult, Place
from apps.api.agentic.catalog import registry
from apps.api.agentic.core_agents import TECH_COMMUNITY, date_window
from apps.api.agentic.router import route

WIRE = {"partial_result", "final_result", "stream_heartbeat", "error"}
BOSTON = Place(lat=42.36, lon=-71.06, name="Boston", city="Boston", country="United States", country_code="US")


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.reset()
    yield
    metrics.reset()


def _line(event, data):
    return orjson.dumps({"event": event, "data": data}) + b"\n"


async def _collect(gen):
    return [json.loads(l) async for l in gen]


# ── routing ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("query,expected", [
    ("tech meetups in Boston this week", ["tech_community"]),
    ("hackathons this weekend", ["tech_community"]),
    ("coffee shops near Boston Common", ["places"]),
    ("concerts in boston tonight", ["live_events"]),
    ("how long is the commute from Back Bay to Kendall Square", ["commute"]),
    ("which neighborhood in Boston is good for families", ["neighborhoods"]),
])
async def test_rules_route(query, expected):
    plan = await route(query, {}, registry)
    assert [a.name for a in plan.agents] == expected and plan.planner == "rules"


@pytest.mark.asyncio
async def test_mixed_ask_selects_several_agents():
    plan = await route("AI startup events and coworking spaces", {}, registry)
    names = {a.name for a in plan.agents}
    assert {"tech_community", "work_study"} <= names


@pytest.mark.asyncio
async def test_llm_planner_used_only_when_rules_fall_back():
    from apps.api.agentic import router as R
    with patch.object(R, "_llm_plan", AsyncMock(return_value=["tech_community"])) as llm:
        plan = await route("anything nerdy going on", {}, registry)
        assert [a.name for a in plan.agents] == ["tech_community"] and plan.planner == "llm"
        await route("coffee shops near Boston Common", {}, registry)
    assert llm.await_count == 1


@pytest.mark.asyncio
async def test_planner_names_are_validated():
    from apps.api.agentic import router as R
    with patch.object(R.settings, "GROQ_API_KEY", None):
        assert await R._llm_plan("x", registry) is None


def test_location_agent_is_not_user_facing():
    assert registry.get("location").manifest.user_facing is False


# ── supervisor ─────────────────────────────────────────────────────────────

def _fake_runtime(final):
    async def gen(query, user_context, *, analyzer=None, metadata=None, run_id=None, **_):
        yield _line("partial_result", {"results": [{"name": "x"}], "status": "ranked"})
        yield _line("stream_heartbeat", {})
        yield _line("final_result", final)
    return gen


@pytest.mark.asyncio
async def test_workflow_only_request_passes_runtime_stream_through():
    final = {"query": "q", "summary": "Hi", "results": [{"name": "Café"}]}
    with patch.object(supervisor, "run_query_ndjson", _fake_runtime(final)):
        events = await _collect(supervisor.run_agents_ndjson("coffee shops near Boston Common", {}))
    assert [e["event"] for e in events] == ["partial_result", "stream_heartbeat", "final_result"]
    assert events[-1]["data"] == final
    assert metrics.snapshot()["places"]["outcomes"] == {"ok": 1}


@pytest.mark.asyncio
async def test_mixed_request_merges_sections_with_status_and_titles():
    final = {"query": "q", "sections": [{"kind": "work", "data": {"results": []}}]}
    tech = AgentResult(agent="tech_community", domain="tech", status="ok",
                       data={"results": [{"title": "AI Meetup"}]})
    with patch.object(supervisor, "run_query_ndjson", _fake_runtime(final)), \
         patch.object(supervisor.LOCATION, "resolve", AsyncMock(return_value=BOSTON)), \
         patch.object(TECH_COMMUNITY, "run", AsyncMock(return_value=tech)):
        events = await _collect(supervisor.run_agents_ndjson("AI startup events and coworking spaces", {}))
    assert {e["event"] for e in events} <= WIRE
    final_ev = events[-1]
    assert final_ev["event"] == "final_result"
    sections = final_ev["data"]["sections"]
    kinds = [s["kind"] for s in sections]
    assert kinds[0] == "tech"                       # content first
    work = next(s for s in sections if s["kind"] == "work")
    assert work["status"] == "empty" and work["title"] == "Work-friendly spots"
    assert "No work-friendly spots" in work["message"] and work["alternatives"]
    assert final_ev["data"]["place"]["city"] == "Boston"
    # The direct agent streamed a partial as soon as it finished.
    assert any(e["event"] == "partial_result" and "section" in e["data"] for e in events)


@pytest.mark.asyncio
async def test_failing_agent_is_isolated_with_positive_message():
    final = {"query": "q", "sections": [{"kind": "work", "data": {"results": [{"name": "Hub"}]}}]}
    with patch.object(supervisor, "run_query_ndjson", _fake_runtime(final)), \
         patch.object(supervisor.LOCATION, "resolve", AsyncMock(return_value=BOSTON)), \
         patch.object(TECH_COMMUNITY, "run", AsyncMock(side_effect=RuntimeError("boom secret"))):
        events = await _collect(supervisor.run_agents_ndjson("AI startup events and coworking spaces", {}))
    raw = json.dumps(events)
    assert "boom secret" not in raw and "RuntimeError" not in raw
    sections = events[-1]["data"]["sections"]
    tech = next(s for s in sections if s["kind"] == "tech")
    assert tech["status"] == "unavailable" and tech["message"]
    assert sections[0]["kind"] == "work"            # the good section leads
    assert metrics.snapshot()["tech_community"]["outcomes"] == {"error": 1}


@pytest.mark.asyncio
async def test_agent_timeout_and_breaker():
    async def slow(task):
        await asyncio.sleep(5)

    with patch.object(TECH_COMMUNITY, "run", slow), \
         patch.object(type(TECH_COMMUNITY), "manifest",
                      TECH_COMMUNITY.manifest.__class__(**{**TECH_COMMUNITY.manifest.__dict__, "timeout_s": 0.05})):
        for _ in range(metrics.BREAKER_THRESHOLD):
            r = await supervisor._run_direct(TECH_COMMUNITY, supervisor.AgentTask("q", {}, BOSTON))
            assert r.status == "unavailable"
        assert metrics.is_open("tech_community")
        r = await supervisor._run_direct(TECH_COMMUNITY, supervisor.AgentTask("q", {}, BOSTON))
    assert metrics.snapshot()["tech_community"]["outcomes"]["skipped"] == 1


# ── tech agent ─────────────────────────────────────────────────────────────

def _ev(title, online=False, locality="city"):
    return {"title": title, "online": online, "locality": locality, "start_date": "2026-10-20"}


@pytest.mark.asyncio
async def test_tech_agent_local_ok():
    from apps.api.agentic import core_agents as C
    out = {"events": [_ev("Boston AI Night"), _ev("Global Hack", True, "online")], "sources": ["luma"]}
    with patch.object(C.events_service, "search", AsyncMock(return_value=out)) as search:
        r = await TECH_COMMUNITY.run(supervisor.AgentTask("tech meetups this week", {}, BOSTON))
    assert r.status == "ok" and [e["title"] for e in r.data["results"]] == ["Boston AI Night"]
    assert r.data["online"][0]["title"] == "Global Hack"
    assert search.call_args.kwargs["category"] == "tech"


@pytest.mark.asyncio
async def test_tech_agent_only_online_is_partial_and_positive():
    from apps.api.agentic import core_agents as C
    out = {"events": [_ev("Global Hack", True, "online")], "sources": []}
    with patch.object(C.events_service, "search", AsyncMock(return_value=out)):
        r = await TECH_COMMUNITY.run(supervisor.AgentTask("hackathons", {}, BOSTON))
    assert r.status == "partial" and "1 you can join online" in r.message


@pytest.mark.asyncio
async def test_tech_agent_nothing_is_positive_empty():
    from apps.api.agentic import core_agents as C
    with patch.object(C.events_service, "search", AsyncMock(return_value={"events": []})):
        r = await TECH_COMMUNITY.run(supervisor.AgentTask("tech", {}, BOSTON))
    assert r.status == "empty" and "Boston" in r.message and r.alternatives


@pytest.mark.parametrize("query,today,expected", [
    ("tonight", date(2026, 10, 21), (date(2026, 10, 21), date(2026, 10, 21))),
    ("this weekend", date(2026, 10, 21), (date(2026, 10, 24), date(2026, 10, 25))),  # Wed → Sat–Sun
    ("this weekend", date(2026, 10, 23), (date(2026, 10, 23), date(2026, 10, 25))),  # Fri → Fri–Sun
    ("this week", date(2026, 10, 21), (date(2026, 10, 21), date(2026, 10, 27))),
    ("anything", date(2026, 10, 21), (date(2026, 10, 21), date(2026, 11, 19))),
])
def test_date_window(query, today, expected):
    assert date_window(query, today) == expected


# ── catalog routes ─────────────────────────────────────────────────────────

def test_agents_routes():
    from fastapi.testclient import TestClient
    from apps.api.main import app
    from apps.api.services import accounts
    c = TestClient(app)
    names = {a["name"] for a in c.get("/v2/agents").json()["agents"]}
    assert {"places", "tech_community", "essentials", "commute"} <= names and "location" not in names
    assert c.get("/v2/agents/health").status_code == 403
    with patch.object(accounts.settings, "AUTH_INTERNAL_SECRET", "s3cret-for-tests-0123456789"):
        r = c.get("/v2/agents/health", headers={"X-Internal-Auth": "s3cret-for-tests-0123456789"})
    assert r.status_code == 200 and "tech_community" in r.json()["agents"]


# ── domain agents & narrator ───────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("query,expected", [
    ("weather in Reykjavik", "weather"),
    ("what should I pack for Boston this week", "weather"),
    ("how do I get around Ubud", "transit"),
    ("is Nairobi safe at night", "safety_health"),
    ("nearest pharmacy", "safety_health"),
    ("what currency do they use in Iceland and should I tip", "money"),
    ("which airport should I fly into for Ubud", "arrival"),
    ("tell me about the local customs in Tokyo", "local_knowledge"),
])
async def test_domain_routes(query, expected):
    plan = await route(query, {}, registry)
    assert plan.agents[0].name == expected and plan.planner == "rules"


@pytest.mark.asyncio
async def test_domain_agent_passes_service_result_through():
    from apps.api.agentic import domain_agents as DA
    svc = AsyncMock(return_value={"status": "ok", "data": {"now": {"temp_c": 5}},
                                  "message": "Clear, 5°C in Boston right now.", "sources": ["open-meteo"]})
    with patch.object(DA, "weather", svc):
        r = await DA.WEATHER.run(supervisor.AgentTask("weather", {}, BOSTON))
    assert r.status == "ok" and r.data["now"]["temp_c"] == 5 and r.message.startswith("Clear")
    assert svc.call_args.args[0].city == "Boston"


@pytest.mark.asyncio
async def test_domain_agent_without_place_asks_politely():
    from apps.api.agentic import domain_agents as DA
    r = await DA.TRANSIT.run(supervisor.AgentTask("how do I get around", {}, None))
    assert r.status == "empty" and "which place" in r.message and r.alternatives


def test_narrator_lead():
    from apps.api.agentic.catalog import NARRATOR
    sections = [{"title": "Weather", "status": "ok"}, {"title": "Tech & community", "status": "partial"},
                {"title": "Getting around", "status": "empty"}]
    assert NARRATOR.lead(sections, "Boston") == "Here's what we found for Boston: weather and tech & community."
    assert "still building up listings" in NARRATOR.lead([{"title": "X", "status": "empty"}], "Tórshavn")


def test_every_user_facing_agent_has_triggers_or_a_workflow():
    for m in registry.manifests():
        if m.user_facing:
            assert m.workflow or m.triggers, m.name


@pytest.mark.asyncio
async def test_explicit_agents_skip_routing_and_ignore_unknown():
    from apps.api.agentic import router as R
    res = AgentResult(agent="weather", domain="weather", status="ok", data={}, message="Clear.")
    with patch.object(R, "route", AsyncMock(side_effect=AssertionError("should not route"))), \
         patch.object(supervisor, "route", AsyncMock(side_effect=AssertionError("should not route"))), \
         patch.object(supervisor.LOCATION, "resolve", AsyncMock(return_value=BOSTON)), \
         patch.object(registry.get("weather"), "run", AsyncMock(return_value=res)):
        events = await _collect(supervisor.run_agents_ndjson("x", {}, agents=["weather", "location", "nope"]))
    sections = events[-1]["data"]["sections"]
    assert [s["agent"] for s in sections] == ["weather"]


def test_today_route_runs_hub_agents():
    from fastapi.testclient import TestClient
    from apps.api.main import app
    from apps.api.routes import today

    seen = {}

    async def fake(query, ctx, *, agents=None, **kw):
        seen.update(query=query, agents=agents)
        yield _line("final_result", {"sections": []})

    with patch.object(today, "run_agents_ndjson", fake):
        r = TestClient(app).post("/v2/today", json={"user_context": {"city": "Boston"}})
    assert r.status_code == 200 and '"final_result"' in r.text
    assert seen["agents"] == today.HUB_AGENTS and "Boston" in seen["query"]


def test_live_events_counts_only_events_not_venues():
    from apps.api.agentic.workflow_agents import LIVE_EVENTS
    venues_only = {"results": [{"type": "Feature", "properties": {"name": "Café"}}]}
    r = LIVE_EVENTS.interpret(venues_only, "Tórshavn")
    assert r.status == "empty" and r.data["results"] == [] and "Tórshavn" in r.message
    with_event = {"results": [{"name": "Show", "dates": {"start": {}}}, {"type": "Feature"}]}
    assert LIVE_EVENTS.interpret(with_event, "Boston").status == "ok"
