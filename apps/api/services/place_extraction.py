"""
Place-entity extraction for conversational queries.

Geocoders expect address-like input. Sending a whole sentence makes them
fuzzy-match on random words: "which neighborhood in Boston is good for
families" anchored on Boston Island, Maine, and "I'm moving to Boston next
month" didn't geocode at all. These helpers pull out just the place phrase
(or the origin/destination pair for commute questions) before geocoding.

Deterministic and dependency-free; no city/country hardcoding.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

MAX_PLACE_LEN = 80

# Phrase after a relocation verb: "moving to Boston", "relocating to Lyon".
# Checked first because "to" is otherwise too ambiguous to treat as a
# location preposition ("to do", "to grab").
_RELOCATION = re.compile(
    r"\b(?:moving|move|moved|relocating|relocate|relocated|transferring)\s+(?:back\s+)?to\s+"
    r"([A-Za-z][\w\s\-'.]{1,60}?)(?=[?!,;]|\.(?:\s|$)|$)",
    re.IGNORECASE,
)

# Phrase after a location preposition ("in", "near", "around", "at", "from").
_LOCATION_PREP = re.compile(
    r"\b(?:in|near|around|at|from|visiting)\s+([A-Za-z][\w\s\-'.]{1,60}?)(?=[?!,;]|\.(?:\s|$)|$)",
    re.IGNORECASE,
)

# "from X to Y" — commute / route questions.
_ROUTE = re.compile(
    r"\bfrom\s+([A-Za-z][\w\s\-'.,]{1,60}?)\s+to\s+([A-Za-z][\w\s\-'.,]{1,60}?)(?=[?!;]|\.(?:\s|$)|$)",
    re.IGNORECASE,
)
# "between X and Y"
_BETWEEN = re.compile(
    r"\bbetween\s+([A-Za-z][\w\s\-'.]{1,60}?)\s+and\s+([A-Za-z][\w\s\-'.]{1,60}?)(?=[?!,;]|\.(?:\s|$)|$)",
    re.IGNORECASE,
)

# Words that start a new clause inside a captured phrase. The candidate is
# cut at the first one: "Boston is good for families" -> "Boston",
# "Boston next month" -> "Boston", "elliot's beach to grab dinner" ->
# "elliot's beach".
_BOUNDARY_WORDS = (
    "to", "for", "and", "but", "or", "so", "where", "that", "while", "because",
    "is", "are", "was", "were", "be", "has", "have", "with", "which", "who",
    "what", "how", "when", "if", "should", "can", "could", "would", "will",
    "do", "does", "next", "this", "last", "tonight", "today", "tomorrow",
    "soon", "by", "during", "within", "like", "good", "best", "please",
    "by car", "by bike", "on foot",
)
_PHRASE_BOUNDARY = re.compile(
    r"\s+(?:" + "|".join(re.escape(w) for w in _BOUNDARY_WORDS) + r")\b",
    re.IGNORECASE,
)

# Leading words that aren't part of the place name ("the", "downtown" kept).
_LEADING_FILLER = re.compile(r"^(?:the|a|an|my|our)\s+", re.IGNORECASE)

# Capitalised multi-word run anywhere in the text: "Boston Common",
# "Kendall Square", "New York". Used when no preposition is present.
_PROPER_NOUN_RUN = re.compile(r"\b([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)*)")
_NOT_PLACES = {"i", "i'm", "im", "i've", "i'd", "what", "which", "where", "how",
               "when", "who", "why", "is", "are", "can", "could", "should",
               "would", "will", "do", "does", "find", "show", "tell", "give",
               "best", "good", "top", "any", "the", "a", "an", "my", "navis",
               "please", "hey", "hi", "hello", "explore", "discover", "visit",
               "visiting", "plan", "help", "recommend", "suggest", "list",
               "search", "looking", "need", "want", "moving", "how long",
               # Capitalized words that are never places.
               "sim", "esim", "atm", "id", "usb", "wifi", "wi-fi", "tv", "pin", "ok",
               "am", "pm", "gps", "faq", "vpn", "sms", "uber", "lyft",
               # "near me" / "around here" mean the user's own location.
               "me", "here", "us", "you", "my location", "my place",
               # Tech abbreviations that collide with country codes (AI = Anguilla).
               "ai", "ml", "vr", "ar", "xr", "it", "ux", "ui", "qa", "hr", "pr", "iot", "api"}


def _clean(candidate: str) -> str:
    candidate = candidate.strip(" ,.;")
    candidate = _PHRASE_BOUNDARY.split(candidate, maxsplit=1)[0].strip(" ,.;")
    candidate = _LEADING_FILLER.sub("", candidate).strip(" ,.;")
    return candidate


def _valid(candidate: str) -> bool:
    return 2 <= len(candidate) <= MAX_PLACE_LEN and candidate.lower() not in _NOT_PLACES


def _proper_noun_place(text: str) -> Optional[str]:
    for m in _PROPER_NOUN_RUN.finditer(text):
        words = m.group(1).split()
        # Drop non-place leading words such as "I'm" or "Which".
        while words and words[0].lower() in _NOT_PLACES:
            words = words[1:]
        candidate = " ".join(words)
        if _valid(candidate):
            return candidate
    return None


def find_place(query: str) -> Optional[str]:
    """The place a query explicitly names ("… in Lisbon", "Boston Common"),
    or None when it names none."""
    raw = (query or "").strip()
    if not raw:
        return None

    for pattern in (_RELOCATION, _LOCATION_PREP):
        for m in pattern.finditer(raw):
            candidate = _clean(m.group(1))
            if _valid(candidate):
                return candidate

    return _proper_noun_place(raw)


def is_activity_query(query: str) -> bool:
    """True for "what/where" asks with no place in them ("good brunch
    spots", "things to do"): they should be anchored on the user's city,
    not geocoded, or a business named "Good Good" wins."""
    from apps.api.runtime.intent.query_intent import QueryIntent, classify_intent

    return find_place(query) is None and classify_intent(query) != QueryIntent.UNKNOWN


def extract_place(query: str) -> str:
    """Reduce a conversational query to its most likely place phrase.

    Falls back to the (length-capped) raw query when nothing place-like is
    found, so plain inputs like "Paris" or "Chennai" pass straight through.
    """
    raw = (query or "").strip()
    found = find_place(raw)
    if found:
        return found
    if len(raw) > MAX_PLACE_LEN:
        return raw[:MAX_PLACE_LEN].strip()
    return raw


def extract_route(query: str) -> Optional[Tuple[str, str]]:
    """Return (origin, destination) phrases for "from X to Y" /
    "between X and Y" questions, or None."""
    raw = (query or "").strip()
    for pattern in (_ROUTE, _BETWEEN):
        m = pattern.search(raw)
        if not m:
            continue
        origin = _clean(m.group(1))
        destination = _clean(m.group(2))
        if _valid(origin) and _valid(destination):
            return origin, destination
    return None
