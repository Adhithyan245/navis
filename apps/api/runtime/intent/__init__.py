"""
Intent analysis — query → list of candidate workflows with confidence scores.

The runtime stays workflow-agnostic; this package owns the mapping from
free-form user queries to workflow names. The default analyzer is a
deterministic keyword classifier with no external dependencies. The ABC
is async so an LLM-backed analyzer can drop in later without changing
callers.
"""
from apps.api.runtime.intent.analyzer import (
    IntentAnalyzer,
    IntentMatch,
    RuleBasedIntentAnalyzer,
    intent_analyzer,
)
from apps.api.runtime.intent.query_intent import (
    EVENT_WORKFLOWS,
    QueryIntent,
    classify_intent,
    has_event_signal,
)

__all__ = [
    "IntentAnalyzer",
    "IntentMatch",
    "RuleBasedIntentAnalyzer",
    "intent_analyzer",
    "QueryIntent",
    "classify_intent",
    "has_event_signal",
    "EVENT_WORKFLOWS",
]
