"""
IntentAnalyzer tests: deterministic classification of representative queries
and graceful fallback when nothing matches.
"""
from __future__ import annotations

import pytest

from apps.api.runtime.intent import IntentMatch, RuleBasedIntentAnalyzer


@pytest.mark.asyncio
async def test_explicit_explore_query_picks_explore_city():
    a = RuleBasedIntentAnalyzer()
    matches = await a.analyze("things to do in chennai this weekend")
    assert matches[0].workflow == "explore_city"
    assert matches[0].confidence >= 0.5


@pytest.mark.asyncio
async def test_work_query_picks_work_mode():
    a = RuleBasedIntentAnalyzer()
    matches = await a.analyze("good coworking spaces with wifi near t nagar")
    assert matches[0].workflow == "work_mode"
    # Multiple strong keywords (coworking + wifi) → confidence well above single-match floor
    assert matches[0].confidence >= 0.5


@pytest.mark.asyncio
async def test_event_query_picks_connect_mode():
    a = RuleBasedIntentAnalyzer()
    matches = await a.analyze("any networking events tonight in mumbai")
    assert matches[0].workflow == "connect_mode"


@pytest.mark.asyncio
async def test_unmatched_query_falls_back_to_explore_city():
    a = RuleBasedIntentAnalyzer()
    matches = await a.analyze("xyzzy plugh")
    assert len(matches) >= 1
    assert matches[0].workflow == "explore_city"
    assert "fallback" in matches[0].reason.lower()


@pytest.mark.asyncio
async def test_multi_signal_query_returns_multiple_workflows():
    """A query mixing event + work signals should surface both above threshold."""
    a = RuleBasedIntentAnalyzer(inclusion_threshold=0.3)
    matches = await a.analyze(
        "find cafes with wifi to work from and any meetup events nearby"
    )
    workflows = [m.workflow for m in matches]
    assert "work_mode" in workflows
    assert "connect_mode" in workflows


@pytest.mark.asyncio
async def test_analyzer_always_returns_at_least_one_match():
    a = RuleBasedIntentAnalyzer()
    for q in ["", "?", "the", "and"]:
        matches = await a.analyze(q)
        assert len(matches) >= 1, f"empty match list for query: {q!r}"


@pytest.mark.asyncio
async def test_intent_match_is_immutable():
    m = IntentMatch(workflow="x", confidence=0.5, reason="r")
    with pytest.raises(Exception):
        m.workflow = "y"  # frozen dataclass
