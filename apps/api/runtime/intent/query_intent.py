"""
Query intent classification + provider/workflow gating.

This is the routing-layer guard that prevents cross-category leakage — most
importantly, it stops event providers (connect_mode → ticketmaster/eventbrite/
meetup) from contaminating non-event queries like "universities in Boston" or
"cafes in Lyon".

Two responsibilities:
  1. `classify_intent(query)` — map a free-form query to ONE strict intent
     (EDUCATION, FOOD, EVENTS, ...). Deterministic, keyword-based, global —
     no city/country hardcoding.
  2. `has_event_signal(query)` + `EVENT_WORKFLOWS` — the precise gate the
     analyzer uses: event workflows may compose ONLY when the query carries an
     explicit event signal. No signal → events are dropped, never substituted.

Kept dependency-free of `analyzer` (no IntentMatch import) so the analyzer can
import these primitives without a cycle.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Dict, Sequence, Tuple


class QueryIntent(str, Enum):
    EDUCATION = "education"
    POI_GENERAL = "poi_general"
    FOOD = "food"
    EVENTS = "events"
    TRANSPORT = "transport"
    HEALTH = "health"
    HOUSING = "housing"
    ENTERTAINMENT = "entertainment"
    UNKNOWN = "unknown"


# Workflows that surface EVENT data. These may only run when the query has an
# explicit event signal — that's the whole anti-leakage rule in one constant.
EVENT_WORKFLOWS = frozenset({"connect_mode"})


_WORD = re.compile(r"[a-z0-9][a-z0-9'\-]+")


def _normalize(query: str) -> str:
    return " ".join(_WORD.findall((query or "").lower()))


def _matches(kw: str, normalized: str) -> bool:
    # Whole-word for short tokens (so "bar" doesn't hit "barber"); substring
    # for longer keywords (preserves plurals like "cafe" → "cafes").
    if len(kw) <= 4 and " " not in kw:
        return f" {kw} " in f" {normalized} "
    return kw in normalized


# Explicit event-intent signals. Presence of ANY of these is what permits an
# event workflow to compose. Deliberately specific to event semantics.
_EVENT_SIGNALS: Tuple[str, ...] = (
    "event", "events", "meetup", "meet up", "networking", "concert", "concerts",
    "gig", "gigs", "festival", "festivals", "live music", "show tonight",
    "shows", "party", "parties", "nightlife", "clubbing", "rave",
    "tickets", "happening tonight", "things happening",
)


# intent → (keyword, weight) pairs. Global vocabulary only.
_INTENT_RULES: Dict[QueryIntent, Sequence[Tuple[str, float]]] = {
    QueryIntent.EDUCATION: [
        ("university", 1.0), ("universities", 1.0), ("college", 1.0),
        ("colleges", 1.0), ("school", 0.9), ("schools", 0.9), ("campus", 0.8),
        ("institute", 0.8), ("academy", 0.8), ("education", 0.8),
        ("kindergarten", 0.9), ("preschool", 0.9), ("tuition", 0.6),
    ],
    QueryIntent.FOOD: [
        ("cafe", 1.0), ("cafes", 1.0), ("coffee", 0.9), ("restaurant", 1.0),
        ("restaurants", 1.0), ("food", 0.7), ("dining", 0.9), ("brunch", 0.9),
        ("bakery", 0.9), ("bistro", 0.9), ("diner", 0.8), ("eatery", 0.9),
        ("pub", 0.7), ("bar", 0.6), ("bars", 0.6),
    ],
    QueryIntent.EVENTS: [
        ("event", 1.0), ("events", 1.0), ("meetup", 1.0), ("networking", 0.9),
        ("concert", 1.0), ("concerts", 1.0), ("gig", 0.9), ("festival", 1.0),
        ("live music", 1.0), ("party", 0.7), ("nightlife", 0.6),
    ],
    QueryIntent.TRANSPORT: [
        ("transit", 1.0), ("metro", 0.9), ("subway", 0.9), ("bus", 0.8),
        ("train", 0.8), ("station", 0.7), ("airport", 0.9), ("commute", 0.9),
        ("transport", 0.9), ("transportation", 0.9), ("tram", 0.8),
    ],
    QueryIntent.HEALTH: [
        ("hospital", 1.0), ("hospitals", 1.0), ("clinic", 1.0), ("clinics", 1.0),
        ("pharmacy", 0.9), ("pharmacies", 0.9), ("doctor", 0.9), ("doctors", 0.9),
        ("dentist", 0.9), ("healthcare", 0.9), ("urgent care", 1.0),
        ("medical", 0.8), ("hospice", 0.8),
    ],
    QueryIntent.HOUSING: [
        ("apartment", 1.0), ("apartments", 1.0), ("rent", 0.8), ("rental", 0.9),
        ("rentals", 0.9), ("housing", 1.0), ("flat", 0.8), ("flats", 0.8),
        ("real estate", 1.0), ("lease", 0.8), ("accommodation", 0.9),
        ("room for rent", 1.0), ("sublet", 0.9),
    ],
    QueryIntent.ENTERTAINMENT: [
        ("cinema", 0.9), ("movie", 0.8), ("movies", 0.8), ("theatre", 0.9),
        ("theater", 0.9), ("museum", 0.9), ("museums", 0.9), ("gallery", 0.8),
        ("galleries", 0.8), ("park", 0.7), ("parks", 0.7), ("attraction", 0.9),
        ("attractions", 0.9), ("things to do", 0.8), ("entertainment", 0.9),
        ("zoo", 0.9), ("aquarium", 0.9), ("sightseeing", 0.9),
    ],
    QueryIntent.POI_GENERAL: [
        ("place", 0.5), ("places", 0.5), ("shop", 0.7), ("shops", 0.7),
        ("shopping", 0.9), ("mall", 0.9), ("store", 0.7), ("stores", 0.7),
        ("gym", 0.9), ("gyms", 0.9), ("fitness", 0.8), ("market", 0.7),
        ("supermarket", 0.9), ("library", 0.8), ("libraries", 0.8),
        ("atm", 0.8), ("bank", 0.7), ("banks", 0.7),
    ],
}


def has_event_signal(query: str) -> bool:
    """True iff the query expresses an explicit event intent."""
    normalized = _normalize(query)
    return any(_matches(sig, normalized) for sig in _EVENT_SIGNALS)


def classify_intent(query: str) -> QueryIntent:
    """
    Classify into ONE strict intent. Highest keyword-weight wins; ties broken
    by a fixed specificity order. No match → UNKNOWN.
    """
    normalized = _normalize(query)
    if not normalized:
        return QueryIntent.UNKNOWN

    scores: Dict[QueryIntent, float] = {}
    for intent, terms in _INTENT_RULES.items():
        score = sum(w for kw, w in terms if _matches(kw, normalized))
        if score > 0:
            scores[intent] = score

    if not scores:
        return QueryIntent.UNKNOWN

    # Specificity order for tie-breaks (most specific first).
    order = [
        QueryIntent.EDUCATION, QueryIntent.HEALTH, QueryIntent.HOUSING,
        QueryIntent.TRANSPORT, QueryIntent.EVENTS, QueryIntent.FOOD,
        QueryIntent.ENTERTAINMENT, QueryIntent.POI_GENERAL,
    ]
    best = max(scores, key=lambda i: (scores[i], -order.index(i) if i in order else 0))
    return best
