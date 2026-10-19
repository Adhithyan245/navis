"""
Regression tests for DEFECT_REPORT.md #1–#10 (backend).

  #1/#2  AI provider model config, humanization fallback, validator probe
  #3     composed workflows: FusionNode `inputs` namespacing
  #4     fusion identity for GeoJSON features
  #6/#7  intent routing + place extraction before geocoding
  #8/#9  rate-limit exemptions and voice payload limit
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from apps.api.models.providers import ProviderResponse
from apps.api.runtime.compose import compose_graphs
from apps.api.runtime.context import NodeResult
from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.nodes.fusion import FusionNode
from apps.api.services.fusion import FusionEngine, item_identity


def _feature(place_id: str, name: str | None, lat: float, lon: float) -> Dict[str, Any]:
    """A Geoapify Places GeoJSON feature: nothing useful at the top level."""
    props: Dict[str, Any] = {"place_id": place_id, "lat": lat, "lon": lon}
    if name:
        props["name"] = name
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def _resp(provider: str, results: list) -> ProviderResponse:
    return ProviderResponse(provider=provider, results=results, confidence=1.0,
                            verified=True, retrieved_at=0.0)


# ── #1 AI provider + humanization ──────────────────────────────────────────

def test_groq_model_is_configurable_and_not_retired():
    from apps.api.core.config import Settings
    s = Settings(_env_file=None)
    assert s.GROQ_MODEL
    assert s.GROQ_MODEL != "llama-3.3-70b-versatile"


def test_ai_provider_uses_configured_model_and_live_hf_host():
    import inspect
    from apps.api.services.providers import ai
    src = inspect.getsource(ai)
    assert "api-inference.huggingface.co/models" not in src
    assert "llama-3.3-70b-versatile" not in src
    assert ai.HF_CHAT_URL.startswith("https://router.huggingface.co/")


def test_extract_chat_text_handles_empty_and_missing():
    from apps.api.services.providers.ai import extract_chat_text
    assert extract_chat_text({"choices": [{"message": {"content": " hi "}}]}) == "hi"
    assert extract_chat_text({"choices": [{"message": {"content": None}}]}) == ""
    assert extract_chat_text({}) == ""


@pytest.mark.asyncio
async def test_format_response_falls_back_to_deterministic_summary():
    from apps.api.services import humanization as h

    failing = AsyncMock(side_effect=ValueError("AI Inference APIs failed"))
    data = {"results": [_feature("a", "Tatte Bakery", 42.35, -71.06),
                        _feature("b", "Thinking Cup", 42.354, -71.064),
                        {"name": "Blue Bottle"}]}
    with patch.object(h.inference_router, "get_inference", failing):
        text = await h.humanization_service.format_response(
            "coffee shops near Boston Common", {"city": "Boston"}, data)

    assert "error" not in text.lower()
    assert "3 results" in text
    assert "Boston" in text
    assert "Tatte Bakery" in text


@pytest.mark.asyncio
async def test_format_response_fallback_when_llm_returns_empty_text():
    from apps.api.services import humanization as h

    empty = AsyncMock(return_value=_resp("AIProvider", [{"text": "   "}]))
    with patch.object(h.inference_router, "get_inference", empty):
        text = await h.humanization_service.format_response("cafes", {}, {"results": []})
    assert "couldn't find" in text
    assert "error" not in text.lower()


@pytest.mark.asyncio
async def test_format_response_uses_llm_text_when_available():
    from apps.api.services import humanization as h

    ok = AsyncMock(return_value=_resp("AIProvider", [{"text": "Try Tatte."}]))
    with patch.object(h.inference_router, "get_inference", ok):
        text = await h.humanization_service.format_response("cafes", {}, {"results": [{"name": "Tatte"}]})
    assert text == "Try Tatte."


# ── #2 validator probes a real completion ──────────────────────────────────

class _FakeResp:
    def __init__(self, status: int, body: dict):
        self.status = status
        self._body = body

    async def json(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, status: int, body: dict):
        self.calls = []
        self._status, self._body = status, body

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResp(self._status, self._body)


@pytest.mark.asyncio
async def test_groq_validator_reports_degraded_when_model_404s():
    from apps.api.services import provider_validator as pv
    session = _FakeSession(404, {"error": {"code": "model_not_found"}})
    with patch.object(pv.settings, "GROQ_API_KEY", "k"):
        state = await pv._validate_groq(session)
    assert state["status"] == "degraded"
    url, kwargs = session.calls[0]
    assert url.endswith("/chat/completions")
    assert kwargs["json"]["model"] == pv.settings.GROQ_MODEL


@pytest.mark.asyncio
async def test_groq_validator_healthy_only_with_completion_text():
    from apps.api.services import provider_validator as pv
    with patch.object(pv.settings, "GROQ_API_KEY", "k"):
        ok = await pv._validate_groq(_FakeSession(200, {"choices": [{"message": {"content": "OK"}}]}))
        empty = await pv._validate_groq(_FakeSession(200, {"choices": [{"message": {"content": ""}}]}))
    assert ok["status"] == "healthy"
    assert empty["status"] == "degraded"


# ── #4 fusion identity ─────────────────────────────────────────────────────

def test_geojson_features_do_not_collapse():
    features = [_feature(f"pid{i}", f"Cafe {i}", 42.35 + i * 0.001, -71.06) for i in range(8)]
    merged = FusionEngine().merge([_resp("PlacesProvider", features)])
    assert merged["total_results"] == 8


def test_geojson_identity_prefers_place_id_then_name_then_coords():
    assert item_identity(_feature("abc", "X", 1, 2)) == "place_id:abc"
    named = {"properties": {"name": "Tatte"}}
    assert item_identity(named) == "name:tatte"
    coords_only = {"properties": {"lat": 42.1, "lon": -71.2}}
    assert item_identity(coords_only).startswith("geo:42.10000,-71.20000")
    geom_only = {"geometry": {"coordinates": [-71.2, 42.1]}}
    assert item_identity(geom_only) == "geo:42.10000,-71.20000"
    assert item_identity({}) is None


def test_duplicate_features_still_dedupe():
    f = _feature("same", "Tatte", 42.35, -71.06)
    merged = FusionEngine().merge([_resp("A", [f]), _resp("B", [dict(f)])])
    assert merged["total_results"] == 1


def test_items_without_identity_are_kept_not_collapsed():
    merged = FusionEngine().merge([_resp("A", [{"foo": 1}, {"foo": 2}])])
    assert merged["total_results"] == 2


def test_fuse_results_handles_geojson():
    out = FusionEngine().fuse_results([{"data": {"places": [
        _feature("1", "A", 1, 1), _feature("2", "B", 2, 2), _feature("3", None, 3, 3)]}}])
    assert len(out["results"]) == 3


# ── #3 composed FusionNode inputs ──────────────────────────────────────────

def _fusion_workflow(workflow_id: str, query_value: str) -> WorkflowGraph:
    return WorkflowGraph.build(
        id=workflow_id, version="1",
        metadata={"section_kind": workflow_id},
        nodes=[
            NodeSpec(id="places_search", type="test.echo", config={"value": query_value}),
            NodeSpec(id="events_search", type="test.echo", config={"value": query_value + "-ev"}),
            NodeSpec(id="fuse_results", type="fusion",
                     depends_on=("places_search", "events_search"),
                     config={"inputs": ["places_search", "events_search"]}),
            NodeSpec(id="final_stream", type="stream", depends_on=("fuse_results",),
                     config={"payload": {"data": "${fuse_results.data}"}}),
        ],
    )


def test_composed_fusion_inputs_are_namespaced_and_match_deps():
    composed = compose_graphs(
        [_fusion_workflow("alpha", "a"), _fusion_workflow("beta", "b")],
        composed_id="ab",
    )
    fusions = [s for s in composed.nodes.values() if s.type == "fusion"]
    assert len(fusions) == 2
    for spec in fusions:
        inputs = spec.config["inputs"]
        assert inputs, spec
        for i in inputs:
            assert "__" in i, f"un-namespaced fusion input {i!r}"
            assert i in spec.depends_on, f"fusion input {i!r} not among deps {spec.depends_on}"


def test_composed_fusion_inputs_follow_dedup_merges():
    # Identical root nodes across workflows get merged by DedupPass; the
    # surviving fusion inputs must point at the kept node.
    composed = compose_graphs(
        [_fusion_workflow("alpha", "same"), _fusion_workflow("beta", "same")],
        composed_id="ab",
    )
    for spec in composed.nodes.values():
        if spec.type == "fusion":
            assert set(spec.config["inputs"]) <= set(spec.depends_on)
            for i in spec.config["inputs"]:
                assert i in composed.nodes


@pytest.mark.asyncio
async def test_composed_fusion_node_fuses_namespaced_dependencies():
    composed = compose_graphs(
        [_fusion_workflow("alpha", "a"), _fusion_workflow("beta", "b")],
        composed_id="ab",
    )
    spec = composed.nodes["alpha__fuse_results"]
    inputs = {
        dep: NodeResult(node_id=dep, ok=True,
                        output=_resp("PlacesProvider", [_feature(dep, dep, 1, 1)]))
        for dep in spec.depends_on
    }
    out = await FusionNode(spec).execute(SimpleNamespace(inputs=inputs))
    assert out["total_results"] == len(spec.depends_on) > 0


# ── #6/#7 intent routing + place extraction ────────────────────────────────

@pytest.mark.parametrize("query,expected", [
    ("how long is the commute from Back Bay to Kendall Square", "commute_analysis"),
    ("which neighborhood in Boston is good for families", "neighborhood_match"),
    ("I'm moving to Boston next month, what should I do", "relocation_plan"),
    ("coffee shops near Boston Common", "explore_city"),
])
def test_intent_routes_common_questions(query, expected):
    from apps.api.runtime.intent.analyzer import RuleBasedIntentAnalyzer
    matches = asyncio.run(RuleBasedIntentAnalyzer().analyze(query))
    assert matches[0].workflow == expected
    assert "default fallback" not in matches[0].reason


@pytest.mark.parametrize("query,place", [
    ("which neighborhood in Boston is good for families", "Boston"),
    ("I'm moving to Boston next month, what should I do", "Boston"),
    ("coffee shops near Boston Common", "Boston Common"),
    ("best cafes in chennai", "chennai"),
    ("things to do in Paris this weekend", "Paris"),
    ("Explore Lyon", "Lyon"),
    ("Paris", "Paris"),
])
def test_extract_place(query, place):
    from apps.api.services.place_extraction import extract_place
    assert extract_place(query) == place


def test_extract_route():
    from apps.api.services.place_extraction import extract_route
    assert extract_route("how long is the commute from Back Bay to Kendall Square") == (
        "Back Bay", "Kendall Square")
    assert extract_route("best cafes in Boston") is None


# ── #8/#9 rate limit + payload limits ──────────────────────────────────────

def test_rate_limit_exemptions():
    from apps.api.core.security import is_rate_limit_exempt
    assert is_rate_limit_exempt("/health")
    assert is_rate_limit_exempt("/providers/status")
    assert is_rate_limit_exempt("/providers/budget")
    assert not is_rate_limit_exempt("/v2/query")
    assert not is_rate_limit_exempt("/interact")


def test_voice_payload_limit_is_raised():
    from apps.api.core.security import MAX_PAYLOAD_BYTES, payload_limit_for
    assert payload_limit_for("/v2/voice") >= 10 * 1024 * 1024
    assert payload_limit_for("/v2/query") == MAX_PAYLOAD_BYTES


def test_health_is_not_rate_limited():
    from fastapi.testclient import TestClient
    from apps.api.core import security
    from apps.api.main import app

    client = TestClient(app)
    with patch.object(security, "MAX_REQUESTS_PER_MINUTE", 0):
        assert client.get("/health").status_code == 200
        assert client.post("/v2/query", json={"query": "x"}).status_code == 429
