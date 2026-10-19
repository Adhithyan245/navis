"""
IntentAnalyzer — pluggable query → workflow classifier.

Default implementation is `RuleBasedIntentAnalyzer`: a deterministic
keyword matcher with no external dependencies. It returns one or more
`IntentMatch` objects sorted by descending confidence. Callers (the
/v2/query route, mostly) consume the top-N and pass them to the
GraphComposer.

Design notes
------------
* `analyze` is async because future analyzers (LLM-backed, embedding
  search, ...) will be I/O bound. The rule-based one happens to be
  synchronous but conforms to the same contract.
* `IntentMatch` includes a `reason` field for traceability. It is
  internal-only — `apps/api/runtime/view.py` does not leak it to the
  wire (intent reasoning is execution mechanics).
* No singleton lock-in: the public `intent_analyzer` is a module-level
  binding routes import; tests substitute it via monkeypatch.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from apps.api.runtime.intent.query_intent import EVENT_WORKFLOWS, has_event_signal


@dataclass(frozen=True)
class IntentMatch:
    """One workflow candidate for a query."""
    workflow: str
    confidence: float       # 0.0 - 1.0
    reason: str             # for logs/tracing — never user-facing


class IntentAnalyzer(ABC):
    @abstractmethod
    async def analyze(
        self,
        query: str,
        user_context: Optional[Mapping[str, Any]] = None,
    ) -> List[IntentMatch]:
        """
        Return ranked workflow candidates. Always returns at least one
        match — implementations must produce a fallback rather than an
        empty list, since `/v2/query` cannot proceed without one.
        """


# ── Rule-based default ──────────────────────────────────────────────────────

# Mapping: workflow → (keyword, weight) pairs. Weights let us bias toward
# strong-signal terms ("coworking" → work_mode) over weak ones ("near" → -).
# Keep this table small and explicit; if the rules get hairy that's the
# signal to swap in an LLM analyzer rather than to grow the table.
_DEFAULT_RULES: Dict[str, Sequence[tuple[str, float]]] = {
    "work_mode": [
        ("coworking", 1.0), ("co-working", 1.0), ("wifi", 0.9), ("laptop", 0.9),
        ("work from", 0.9), ("remote work", 1.0), ("cafe", 0.5),
        ("study", 0.6), ("focus", 0.4), ("workspace", 0.9),
    ],
    "connect_mode": [
        ("event", 0.9), ("events", 0.9), ("meetup", 1.0), ("networking", 1.0),
        ("concert", 0.9), ("show tonight", 0.9), ("happening", 0.7),
        ("party", 0.7), ("gig", 0.8), ("live music", 0.9),
        # Natural-language meet phrases that previously fell through to fallback.
        ("meet up", 1.0), ("meet people", 1.0), ("new people", 0.9),
        ("hangout", 0.9), ("hang out", 0.8),
        # Community/network terms; "network" is lower because it can also mean wifi.
        ("community", 0.7), ("communities", 0.7), ("network", 0.5),
        # Domain-specific signals seen in the wild (AI, startup, tech scenes).
        ("ai", 0.7), ("artificial intelligence", 1.0),
        ("tech people", 1.0), ("tech scene", 0.9),
        ("founder", 0.6), ("founders", 0.6),
        ("startup", 0.5), ("startups", 0.5),
    ],
    "explore_city": [
        ("explore", 1.0), ("discover", 0.9), ("things to do", 1.0),
        ("places to visit", 0.9), ("tourist", 0.8), ("sightseeing", 0.9),
        ("what to do", 0.8), ("new to", 0.6), ("visiting", 0.7),
        # First-time-in-city framings that previously matched no rule.
        ("first time", 0.6), ("new in", 0.6),
        # Everyday POI asks ("coffee shops near ...") — explore_city is the
        # POI workflow, so route here explicitly instead of via fallback.
        ("coffee", 0.6), ("restaurant", 0.6), ("places to eat", 0.8),
        ("where to eat", 0.8), ("shops", 0.4),
    ],
    # Phase 4 — origin→destination travel estimates.
    "commute_analysis": [
        ("commute", 1.0), ("commuting", 1.0), ("travel time", 1.0),
        ("how long does it take", 0.8), ("how long", 0.5), ("how far", 0.8),
        ("drive from", 0.9), ("get from", 0.8), ("route from", 0.9),
        ("directions from", 0.9), ("distance from", 0.8), ("distance between", 0.9),
    ],
    # Phase 3A — where-to-live questions.
    "neighborhood_match": [
        ("neighborhood", 1.0), ("neighbourhood", 1.0),
        ("where to live", 1.0), ("where should live", 1.0),
        ("area to live", 0.9), ("areas to live", 0.9), ("place to live", 0.8),
        ("good for families", 0.6), ("family friendly", 0.6),
        ("family-friendly", 0.6), ("safe area", 0.7),
    ],
    # Phase 2 — relocation planning + checklists.
    # Keep phrases multi-word and specific to avoid colliding with the broader
    # explore/connect rules above. Single tokens like "plan" or "checklist"
    # would over-trigger; the phrases below are typically only used by
    # someone actually thinking about a move.
    "relocation_plan": [
        ("relocation plan", 1.0), ("moving plan", 1.0),
        ("settling in", 0.9), ("getting settled", 0.9),
        ("just moved", 0.9), ("recently moved", 0.9),
        ("relocating to", 0.9), ("moving to a new city", 1.0),
        # Plain move announcements ("I'm moving to Boston next month").
        ("moving to", 0.9), ("move to", 0.8), ("relocating", 0.8),
        ("relocate to", 0.9), ("moving here", 0.8),
    ],
    "essentials_checklist": [
        ("relocation checklist", 1.0), ("moving checklist", 1.0),
        ("move-in checklist", 1.0), ("settle in checklist", 1.0),
        ("essentials after moving", 1.0),
        ("relocation to do", 0.9), ("relocation to-do", 0.9),
        # The query normalizer strips single-letter tokens ("I", "a") to
        # cut stopword noise. So phrases like "what do I need to do" end
        # up as "what do need to do" pre-match. The keywords below survive
        # that stripping and catch "what do I need to do first" / "what
        # should I do first" / "what to do first" style queries.
        ("need to do", 0.9), ("should do first", 0.9),
    ],
}

# Confidence threshold for a workflow to be included in a multi-workflow
# composition. Below this, it's considered noise relative to the top match.
_INCLUSION_THRESHOLD = 0.45

# Workflow used when no rule fires at all.
_DEFAULT_FALLBACK = "explore_city"


_WORD_BOUNDARY = re.compile(r"[a-z0-9][a-z0-9'\-]+")


def _normalize(query: str) -> str:
    return " ".join(_WORD_BOUNDARY.findall(query.lower()))


def _matches(kw: str, normalized: str) -> bool:
    """Substring match for longer keywords (preserves plural matching like
    'cafe' → 'cafes'); whole-word match for short keywords (so 'ai' does
    not match 'available' or 'rain').
    """
    if len(kw) <= 3:
        return f" {kw} " in f" {normalized} "
    return kw in normalized


class RuleBasedIntentAnalyzer(IntentAnalyzer):
    def __init__(
        self,
        rules: Optional[Mapping[str, Sequence[tuple[str, float]]]] = None,
        *,
        inclusion_threshold: float = _INCLUSION_THRESHOLD,
        fallback_workflow: str = _DEFAULT_FALLBACK,
    ) -> None:
        self._rules = rules or _DEFAULT_RULES
        self._threshold = inclusion_threshold
        self._fallback = fallback_workflow

    async def analyze(
        self,
        query: str,
        user_context: Optional[Mapping[str, Any]] = None,
    ) -> List[IntentMatch]:
        normalized = _normalize(query)

        matches: List[IntentMatch] = []
        for workflow, terms in self._rules.items():
            score = 0.0
            hits: List[str] = []
            for kw, weight in terms:
                if _matches(kw, normalized):
                    score += weight
                    hits.append(kw)
            if score <= 0:
                continue
            # Squash to [0, 1) with diminishing returns past 2 strong hits.
            confidence = 1.0 - 1.0 / (1.0 + score)
            matches.append(IntentMatch(
                workflow=workflow,
                confidence=round(confidence, 3),
                reason=f"matched {hits}",
            ))

        matches.sort(key=lambda m: m.confidence, reverse=True)

        if not matches:
            return [IntentMatch(
                workflow=self._fallback,
                confidence=0.3,
                reason="no rule matched; default fallback",
            )]

        # Always keep the top match; additionally include any others above
        # the inclusion threshold for multi-workflow composition.
        top = matches[0]
        others = [m for m in matches[1:] if m.confidence >= self._threshold]
        selected = [top, *others]

        # ── Provider gating (anti cross-category leakage) ──────────────────
        # Event workflows may compose ONLY when the query carries an explicit
        # event signal. Otherwise drop them — never let concerts/meetups leak
        # into "universities", "cafes", "hospitals", ... queries. We never
        # substitute unrelated providers: if gating empties the set, we fall
        # back to the POI default, not to events.
        if not has_event_signal(query):
            gated = [m for m in selected if m.workflow not in EVENT_WORKFLOWS]
            if gated:
                selected = gated
            else:
                return [IntentMatch(
                    workflow=self._fallback,
                    confidence=0.3,
                    reason="gated: event workflow rejected for non-event query; default POI",
                )]
        return selected


# Module-level binding the route imports. Tests can monkeypatch.
intent_analyzer: IntentAnalyzer = RuleBasedIntentAnalyzer()
