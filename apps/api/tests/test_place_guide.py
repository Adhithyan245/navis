"""Place-specific essentials: generator validation, caching, and how the
retrieval node uses it (LLM mocked; no network)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.api.runtime.graph import NodeSpec
from apps.api.runtime.nodes.context import ContextRetrievalNode
from apps.api.services import place_guide as PG
from apps.api.services.context_retriever import MarkdownRetriever

LLM_JSON = {"items": [
    {"title": "Get a Strætó Klapp card", "detail": "Buy it online or at Mjódd.", "urgency": "high",
     "stage": "week_1", "topic": "transit", "official_url": "https://straeto.is"},
    {"title": "Save 112", "detail": "One number for police, fire and ambulance.", "urgency": "URGENT",
     "stage": "someday", "topic": "weird", "official_url": "javascript:alert(1)"},
    {"title": "Get a Strætó Klapp card", "detail": "duplicate", "urgency": "low"},
    {"title": "x"},
    "not a dict",
]}


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path):
    with patch.object(PG, "_cache_dir", lambda: tmp_path / "guides"), \
         patch.object(PG, "_drop_dead_links", AsyncMock()):
        PG._locks.clear()
        yield


def test_clean_items_validates_and_clamps():
    items = PG._clean_items(LLM_JSON, city="Reykjavik", key="is-reykjavik")
    titles = [i["frontmatter"]["title"] for i in items]
    assert titles == ["Get a Strætó Klapp card", "Save 112"]  # dup, too-short, non-dict dropped
    first, second = (i["frontmatter"] for i in items)
    assert first["external_link"] == "https://straeto.is" and first["generated"] is True
    assert first["id"].startswith("is-reykjavik-") and first["city"] == "reykjavik"
    assert second["urgency"] == "medium" and second["stage"] == "week_1"   # clamped
    assert "external_link" not in second                                  # unsafe URL dropped
    assert items[0]["body"] == "Buy it online or at Mjódd."


@pytest.mark.asyncio
async def test_guide_is_generated_once_then_cached():
    ask = AsyncMock(return_value=LLM_JSON)
    with patch.object(PG, "_ask_llm", ask):
        a = await PG.guide_for("Reykjavik", country_code="IS", country="Iceland")
        b = await PG.guide_for("Reykjavik", country_code="IS", country="Iceland")
    # One draft + one review call, then served from cache.
    assert ask.await_count == 2 and a == b and len(a) == 2
    draft_prompt, review_prompt = (c.args[0] for c in ask.call_args_list)
    assert "Reykjavik, Iceland" in draft_prompt
    assert "Fact-check it for Reykjavik, Iceland" in review_prompt


@pytest.mark.asyncio
async def test_llm_failure_returns_empty_and_is_not_cached():
    with patch.object(PG, "_ask_llm", AsyncMock(return_value=None)):
        assert await PG.guide_for("Nowhere", country_code="XX") == []
    with patch.object(PG, "_ask_llm", AsyncMock(return_value=LLM_JSON)) as ask:
        assert len(await PG.guide_for("Nowhere", country_code="XX")) == 2
    assert ask.await_count == 2  # draft + review; the earlier miss wasn't cached


@pytest.mark.asyncio
async def test_review_pass_output_is_used():
    reviewed = {"items": [{"title": "Get the local bus card", "detail": "Generic.", "urgency": "high",
                           "stage": "week_1", "topic": "transit", "official_url": None}]}
    ask = AsyncMock(side_effect=[LLM_JSON, reviewed])
    with patch.object(PG, "_ask_llm", ask):
        items = await PG.guide_for("Torshavn", country_code="FO")
    assert [i["frontmatter"]["title"] for i in items] == ["Get the local bus card"]


@pytest.mark.asyncio
async def test_unusable_review_keeps_draft():
    ask = AsyncMock(side_effect=[LLM_JSON, {"items": []}])
    with patch.object(PG, "_ask_llm", ask):
        items = await PG.guide_for("Torshavn", country_code="FO")
    assert len(items) == 2


@pytest.mark.asyncio
async def test_no_key_means_no_call():
    with patch.object(PG.settings, "GROQ_API_KEY", None):
        assert await PG._ask_llm("x") is None


def test_place_key_is_per_country():
    assert PG.place_key("Cambridge", "US") != PG.place_key("Cambridge", "GB")


# ── retrieval node ─────────────────────────────────────────────────────────

def _corpus(tmp_path) -> MarkdownRetriever:
    root = tmp_path / "knowledge"
    (root / "cities" / "boston").mkdir(parents=True)
    (root / "universal").mkdir()
    (root / "cities" / "boston" / "mbta.md").write_text(
        "---\nid: boston-mbta\ntitle: Get a CharlieCard\nurgency: high\ncity: boston\n"
        "tags: [essentials, checklist]\n---\nMBTA card.\n", encoding="utf-8")
    (root / "universal" / "bank.md").write_text(
        "---\nid: universal-bank\ntitle: Update banking\nurgency: high\n"
        "tags: [essentials, checklist]\n---\nBanks.\n", encoding="utf-8")
    r = MarkdownRetriever()
    r.load(root)
    return r


def _ctx(user):
    return SimpleNamespace(query="Essentials checklist", user_context=user, inputs={},
                           execution=SimpleNamespace(user_context=user, query="q"))


async def _run(tmp_path, user, guide):
    spec = NodeSpec(id="retrieve", type="context_retrieval", config={
        "city": user.get("city"), "place": user.get("cityLocation"),
        "tags": ["essentials", "checklist"], "limit": 40, "generate_local": True})
    from apps.api.runtime.nodes import context as node_mod
    with patch.object(node_mod, "context_retriever", _corpus(tmp_path)), \
         patch.object(node_mod, "guide_for", guide), \
         patch.object(node_mod, "resolve", lambda v, ctx: v):
        return await ContextRetrievalNode(spec).execute(_ctx(user))


@pytest.mark.asyncio
async def test_hand_written_city_does_not_generate(tmp_path):
    guide = AsyncMock(return_value=[])
    out = await _run(tmp_path, {"city": "Boston"}, guide)
    ids = [c["frontmatter"]["id"] for c in out["chunks"]]
    assert "boston-mbta" in ids and "universal-bank" in ids
    guide.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_city_gets_generated_items_first_and_no_boston(tmp_path):
    generated = PG._clean_items(LLM_JSON, city="Reykjavik", key="is-reykjavik")
    guide = AsyncMock(return_value=generated)
    out = await _run(tmp_path, {"city": "Reykjavik",
                                "cityLocation": {"country_code": "IS", "country": "Iceland"}}, guide)
    ids = [c["frontmatter"]["id"] for c in out["chunks"]]
    assert ids[0].startswith("is-reykjavik-")
    assert "universal-bank" in ids and "boston-mbta" not in ids
    kwargs = guide.call_args.kwargs
    assert kwargs["country_code"] == "IS" and "Update banking" in kwargs["exclude_titles"]


@pytest.mark.asyncio
async def test_generator_down_falls_back_to_universal(tmp_path):
    out = await _run(tmp_path, {"city": "Reykjavik"}, AsyncMock(return_value=[]))
    assert [c["frontmatter"]["id"] for c in out["chunks"]] == ["universal-bank"]


def test_no_city_never_returns_city_pinned_chunks(tmp_path):
    r = _corpus(tmp_path)
    ids = [c.frontmatter["id"] for c in r.retrieve("essentials", city=None, tags=["essentials"], limit=10)]
    assert ids == ["universal-bank"]
