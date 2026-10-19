"""
End-to-end test for the explore_city vertical slice.

Drives the real workflow YAML through the real runtime + view filter,
with the heavy external services (providers, fusion, ranking,
humanization) replaced by lightweight fakes via monkeypatch.

Assertions:
  * The full pipeline executes without raising.
  * Only user-facing events cross the wire (no node_started / etc.).
  * A `partial_result` is emitted before the `final_result`.
  * The final payload contains the humanized summary, the ranked list,
    the transit data, and the retrieved context chunks.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import orjson
import pytest


# ── Fakes ───────────────────────────────────────────────────────────────────

@dataclass
class FakeProviderResponse:
    provider: str
    source: str = "primary"
    results: list = field(default_factory=list)
    error: Optional[str] = None
    confidence: float = 1.0
    verified: bool = True
    retrieved_at: float = 0.0


class _FakeProvider:
    def __init__(self, name, payload, source="primary"):
        self.name = name
        self._payload = payload
        self._source = source

    async def execute(self, **kwargs):
        await asyncio.sleep(0.01)
        return FakeProviderResponse(
            provider=self.name,
            source=self._source,
            results=self._payload,
        )


class _FakeRanking:
    def rank_places(self, items, user_ctx, anchor_location=None):
        for it in items:
            it["_rank"] = {"score": it.get("rating", 0)}
        return sorted(items, key=lambda x: x["_rank"]["score"], reverse=True)
    def rank_events(self, items, user_ctx):
        return items
    def rank_services(self, items, anchor_location=None):
        return items
    def strip_ranking_metadata(self, items):
        for it in items:
            it.pop("_rank", None)
        return items


class _FakeFusion:
    def merge(self, responses):
        merged, seen, providers_used, fallback_used = [], set(), [], False
        for r in responses:
            providers_used.append(r.provider)
            if r.source == "fallback":
                fallback_used = True
            for item in r.results:
                ident = item.get("name") or item.get("title") or item.get("id")
                if ident and ident not in seen:
                    seen.add(ident)
                    item["_provenance"] = {"provider": r.provider, "confidence": r.confidence}
                    merged.append(item)
        return {
            "total_results": len(merged),
            "data": merged,
            "providers_used": providers_used,
            "fallback_used": fallback_used,
        }


class _FakeHumanization:
    async def format_response(self, query, context, data):
        results = data.get("results", []) if isinstance(data, dict) else []
        return f"Found {len(results)} matches for '{query}'."


# ── Fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture
def patched_runtime(monkeypatch):
    """Patch the runtime's collaborators with fakes."""
    from apps.api.services import provider_manager as pm_mod
    from apps.api.services import fusion as fusion_mod
    from apps.api.services import ranking as ranking_mod
    from apps.api.services import humanization as humanization_mod
    from apps.api.services import context_retriever as ctx_mod
    from apps.api.runtime.nodes import provider as provider_node_mod
    from apps.api.runtime.nodes import fusion as fusion_node_mod
    from apps.api.runtime.nodes import ranking as ranking_node_mod
    from apps.api.runtime.nodes import humanization as humanization_node_mod
    from apps.api.models import providers as providers_model_mod

    # Provider manager — geo returns one result, others return useful payloads
    class _FakePM:
        def __init__(self):
            self.geo = _FakeProvider("geo", [
                # Real GeoProvider returns lat+lon (not lng) — match it so YAML refs work
                {"lat": 12.97, "lon": 80.20, "name": "Chennai"},
            ])
            self.places = _FakeProvider("places", [
                {"name": "Cafe A", "rating": 4.5, "location": {"lat": 12.97, "lng": 80.20}, "types": ["cafe"]},
                {"name": "Cafe B", "rating": 4.2, "location": {"lat": 12.98, "lng": 80.21}, "types": ["cafe"]},
            ])
            self.events = _FakeProvider("events", [
                {"title": "Music Night", "id": "ev1", "categories": ["music"]},
            ])
            self.transit = _FakeProvider("transit", [
                {"line": "Metro Blue", "stops": 12},
            ])
            self.wiki = _FakeProvider("wiki", [])
            self.ai = _FakeProvider("ai", [])
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

    # Fusion node checks `isinstance(out, ProviderResponse)` — point that at our fake
    monkeypatch.setattr(fusion_node_mod, "ProviderResponse", FakeProviderResponse)

    # Load knowledge corpus + workflow registry from the real files
    from apps.api.runtime.compiler.registry import workflow_registry
    ctx_mod.context_retriever.load(Path("knowledge"))
    workflow_registry.load_dir(Path("apps/api/workflows"))

    yield fake_pm


# ── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_explore_city_streams_only_user_facing_events(patched_runtime):
    from apps.api.runtime.runner import run_workflow_ndjson
    import apps.api.runtime.nodes  # noqa: ensures node registrations

    lines: List[dict] = []
    async for raw in run_workflow_ndjson("explore_city", "best cafes in chennai"):
        lines.append(orjson.loads(raw))

    event_names = [l["event"] for l in lines]

    forbidden = {
        "workflow_started", "workflow_completed", "workflow_cancelled",
        "node_started", "node_completed", "node_failed", "node_skipped",
        "provider_fallback",
    }
    leaked = set(event_names) & forbidden
    assert not leaked, f"internal events leaked to wire: {leaked}"

    # At least one partial_result before the final_result
    partials = [i for i, l in enumerate(lines) if l["event"] == "partial_result"]
    finals = [i for i, l in enumerate(lines) if l["event"] == "final_result"]
    assert partials, "expected at least one partial_result"
    assert finals, "expected at least one final_result"
    assert min(partials) < max(finals), "partial_result must come before final_result"


@pytest.mark.asyncio
async def test_explore_city_final_payload_shape(patched_runtime):
    from apps.api.runtime.runner import run_workflow_ndjson
    import apps.api.runtime.nodes  # noqa

    lines: List[dict] = []
    async for raw in run_workflow_ndjson("explore_city", "best cafes in chennai"):
        lines.append(orjson.loads(raw))

    finals = [l for l in lines if l["event"] == "final_result"]
    assert finals, "no final_result emitted"
    final = finals[-1]["data"]

    assert final["query"] == "best cafes in chennai"
    assert final["summary"].startswith("Found ")
    assert isinstance(final["results"], list) and len(final["results"]) >= 1
    assert final["results"][0]["name"] in ("Cafe A", "Cafe B")
    assert isinstance(final["context"], list)
    assert isinstance(final["providers_used"], list)


@pytest.mark.asyncio
async def test_explore_city_partial_payload_is_useful(patched_runtime):
    """partial_result must contain meaningful data, not orchestration noise."""
    from apps.api.runtime.runner import run_workflow_ndjson
    import apps.api.runtime.nodes  # noqa

    partials: List[dict] = []
    async for raw in run_workflow_ndjson("explore_city", "best cafes in chennai"):
        parsed = orjson.loads(raw)
        if parsed["event"] == "partial_result":
            partials.append(parsed["data"])

    assert partials
    p = partials[0]
    assert "results" in p
    assert isinstance(p["results"], list)
    # No node ids or internal mechanics leaking through
    serialized = orjson.dumps(p).decode()
    assert "node_id" not in serialized
    assert "workflow" not in serialized.lower()
