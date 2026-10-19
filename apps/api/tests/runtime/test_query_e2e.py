"""
End-to-end /v2/query tests.

Drives the real intent analyzer + composer + runtime against stubbed
providers, asserting:
  * Single-workflow queries route correctly and emit a single final_result.
  * Multi-workflow queries compose into one execution and emit ONE
    final_result with multiple sections.
  * Provider calls dedupe across composed workflows (geo_search runs once).
  * Invisible-orchestration rule holds for both paths.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import orjson
import pytest


# ── Fakes shared with test_explore_city_e2e but call-counted ───────────────

@dataclass
class FakeProviderResponse:
    provider: str
    source: str = "primary"
    results: list = field(default_factory=list)
    error: Optional[str] = None
    confidence: float = 1.0
    verified: bool = True
    retrieved_at: float = 0.0


class _CountingProvider:
    def __init__(self, name, payload):
        self.name = name
        self._payload = payload
        self.call_count = 0
        self.call_args = []

    async def execute(self, **kwargs):
        self.call_count += 1
        self.call_args.append(kwargs)
        await asyncio.sleep(0.005)
        return FakeProviderResponse(provider=self.name, results=self._payload)


class _FakeFusion:
    def merge(self, responses):
        merged, seen = [], set()
        for r in responses:
            for item in r.results:
                ident = item.get("name") or item.get("title") or item.get("id")
                if ident and ident not in seen:
                    seen.add(ident)
                    item["_provenance"] = {"provider": r.provider, "confidence": r.confidence}
                    merged.append(item)
        return {
            "total_results": len(merged),
            "data": merged,
            "providers_used": [r.provider for r in responses],
            "fallback_used": False,
        }


class _FakeRanking:
    def rank_places(self, items, user_ctx, anchor_location=None):
        return sorted(items, key=lambda x: x.get("rating", 0), reverse=True)
    def rank_events(self, items, user_ctx):
        return items
    def rank_services(self, items, anchor_location=None):
        return items
    def strip_ranking_metadata(self, items):
        return items


class _FakeHumanization:
    async def format_response(self, query, context, data):
        results = data.get("results", []) if isinstance(data, dict) else []
        return f"Found {len(results)} matches for '{query}'."


# ── Fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture
def patched_query_runtime(monkeypatch):
    """Patch collaborators and load real workflows + knowledge corpus."""
    from apps.api.services import provider_manager as pm_mod
    from apps.api.services import fusion as fusion_mod
    from apps.api.services import ranking as ranking_mod
    from apps.api.services import humanization as humanization_mod
    from apps.api.services import context_retriever as ctx_mod
    from apps.api.runtime.nodes import provider as provider_node_mod
    from apps.api.runtime.nodes import fusion as fusion_node_mod
    from apps.api.runtime.nodes import ranking as ranking_node_mod
    from apps.api.runtime.nodes import humanization as humanization_node_mod

    class _FakePM:
        def __init__(self):
            self.geo = _CountingProvider("geo", [
                {"lat": 12.97, "lon": 80.20, "name": "Chennai"},
            ])
            self.places = _CountingProvider("places", [
                {"name": "Cafe A", "rating": 4.5, "location": {"lat": 12.97, "lng": 80.20}, "types": ["cafe"]},
                {"name": "Cafe B", "rating": 4.2, "location": {"lat": 12.98, "lng": 80.21}, "types": ["cafe"]},
            ])
            self.events = _CountingProvider("events", [
                {"title": "Music Night", "id": "ev1", "categories": ["music"]},
                {"title": "Networking Meetup", "id": "ev2", "categories": ["networking"]},
            ])
            self.transit = _CountingProvider("transit", [])
            self.wiki = _CountingProvider("wiki", [])
            self.ai = _CountingProvider("ai", [])
            self.session = None
            self.semaphore = asyncio.Semaphore(20)

    fake_pm = _FakePM()
    monkeypatch.setattr(pm_mod, "provider_manager", fake_pm)
    monkeypatch.setattr(provider_node_mod, "provider_manager", fake_pm)

    fake_ranking = _FakeRanking()
    monkeypatch.setattr(ranking_mod, "ranking_service", fake_ranking)
    monkeypatch.setattr(ranking_node_mod, "ranking_service", fake_ranking)

    fake_fusion = _FakeFusion()
    monkeypatch.setattr(fusion_mod, "fusion_engine", fake_fusion)
    monkeypatch.setattr(fusion_node_mod, "fusion_engine", fake_fusion)

    fake_hum = _FakeHumanization()
    monkeypatch.setattr(humanization_mod, "humanization_service", fake_hum)
    monkeypatch.setattr(humanization_node_mod, "humanization_service", fake_hum)

    monkeypatch.setattr(fusion_node_mod, "ProviderResponse", FakeProviderResponse)

    # Load real workflows + knowledge corpus
    from apps.api.runtime.compiler.registry import workflow_registry
    workflow_registry.clear()
    ctx_mod.context_retriever.load(Path("knowledge"))
    workflow_registry.load_dir(Path("apps/api/workflows"))

    yield fake_pm


# ── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_workflow_query_routes_to_explore_city(patched_query_runtime):
    """A pure 'discover' query should fan out only to explore_city."""
    from apps.api.runtime.runner import run_query_ndjson
    import apps.api.runtime.nodes  # noqa

    lines = []
    async for raw in run_query_ndjson("things to do in chennai this weekend"):
        lines.append(orjson.loads(raw))

    finals = [l for l in lines if l["event"] == "final_result"]
    assert len(finals) == 1, f"expected exactly 1 final_result, got {len(finals)}"

    payload = finals[0]["data"]
    # Single-workflow short-circuit: aggregator NOT involved, so payload
    # has the explore_city shape directly (no `sections` key).
    assert "sections" not in payload
    assert payload["query"] == "things to do in chennai this weekend"
    assert isinstance(payload["results"], list)


@pytest.mark.asyncio
async def test_multi_workflow_query_composes_into_one_final(patched_query_runtime):
    """A mixed query picks multiple workflows; result has one final_result with sections."""
    from apps.api.runtime.runner import run_query_ndjson
    import apps.api.runtime.nodes  # noqa

    query = "find cafes with wifi to work from and any meetup events nearby"
    lines = []
    async for raw in run_query_ndjson(query):
        lines.append(orjson.loads(raw))

    finals = [l for l in lines if l["event"] == "final_result"]
    assert len(finals) == 1, f"expected exactly 1 final_result, got {len(finals)}"

    payload = finals[0]["data"]
    assert payload["query"] == query
    sections = payload["sections"]
    assert isinstance(sections, list) and len(sections) >= 2

    kinds = {s["kind"] for s in sections}
    assert kinds & {"work", "events"}, f"expected work + events sections, got {kinds}"

    # Each section's data is the resolved upstream stream payload, not a literal ref
    for s in sections:
        assert isinstance(s["data"], dict)
        assert "${" not in orjson.dumps(s["data"]).decode()


@pytest.mark.asyncio
async def test_geo_provider_dedupes_across_composed_workflows(patched_query_runtime):
    """work_mode + connect_mode both start with `provider geo args=${ctx.query}` —
    composer dedup should cause exactly ONE geo provider call."""
    from apps.api.runtime.runner import run_query_ndjson
    import apps.api.runtime.nodes  # noqa

    fake_pm = patched_query_runtime
    async for _ in run_query_ndjson(
        "coworking cafes and networking events near electronic city"
    ):
        pass

    assert fake_pm.geo.call_count == 1, (
        f"geo provider was called {fake_pm.geo.call_count} times — "
        f"dedup didn't fire"
    )


@pytest.mark.asyncio
async def test_query_route_emits_only_user_facing_events(patched_query_runtime):
    from apps.api.runtime.runner import run_query_ndjson
    import apps.api.runtime.nodes  # noqa

    forbidden = {
        "workflow_started", "workflow_completed", "workflow_cancelled",
        "node_started", "node_completed", "node_failed", "node_skipped",
        "provider_fallback",
    }

    seen = set()
    async for raw in run_query_ndjson("cafes to work from in mumbai"):
        seen.add(orjson.loads(raw)["event"])

    leaked = seen & forbidden
    assert not leaked, f"internal events leaked through /v2/query: {leaked}"


@pytest.mark.asyncio
async def test_partial_results_precede_final_in_multi_workflow(patched_query_runtime):
    from apps.api.runtime.runner import run_query_ndjson
    import apps.api.runtime.nodes  # noqa

    events_order = []
    async for raw in run_query_ndjson(
        "work-friendly cafes and live music events"
    ):
        events_order.append(orjson.loads(raw)["event"])

    first_final = events_order.index("final_result")
    partials_before = [i for i, e in enumerate(events_order) if e == "partial_result" and i < first_final]
    assert partials_before, "expected at least one partial_result before final_result"


@pytest.mark.asyncio
async def test_unmatched_query_still_resolves_via_fallback(patched_query_runtime):
    """No keywords match → analyzer's fallback (explore_city) runs successfully."""
    from apps.api.runtime.runner import run_query_ndjson
    import apps.api.runtime.nodes  # noqa

    finals = []
    async for raw in run_query_ndjson("xyzzy plugh"):
        parsed = orjson.loads(raw)
        if parsed["event"] == "final_result":
            finals.append(parsed["data"])

    assert len(finals) == 1
    assert finals[0]["query"] == "xyzzy plugh"
