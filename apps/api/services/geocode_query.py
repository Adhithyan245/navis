"""
Query preparation for location search: the parts that make typed addresses
behave more like they do in Google Maps.

* `normalize_query` — drop apartment/unit designators ("Apt 3", "#2B",
  "Suite 100") that geocoders choke on, and expand common street-type
  abbreviations ("Kendall Sq" → "Kendall Square", "Back Bay Stn" →
  "Back Bay Station") that autocomplete endpoints often miss.
* `looks_like_acronym` — "MIT", "NEU", "JP", "NYC": short tokens that a
  geocoder can't resolve by spelling alone.
* `expand_acronym` — last-resort expansion of such a token with a fast LLM,
  in the context of the user's city ("NEU" near Boston → "Northeastern
  University"). Cached; never raises; returns None when unsure.

Global vocabulary only — no city-specific alias tables.
"""
from __future__ import annotations

import re
from typing import Optional

import aiohttp

from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache

logger = get_logger(__name__)

# ── Unit / apartment designators ────────────────────────────────────────────
# The unit value must contain a digit or be a single letter, so words like
# "Ste-Foy" or "Floor" in a place name survive.
_UNIT = re.compile(
    r"(?:,\s*|\s+)(?:apt|apartment|unit|suite|ste|fl|floor|rm|room|bldg|building)\.?\s*"
    r"(?:no\.?\s*)?(?:#\s*)?(?:[a-z]?\d[\w-]*|[a-z])\b"
    r"|\s*#\s*[a-z]?\d[\w-]*\b",
    re.IGNORECASE,
)

# ── Street-type abbreviations (expanded only after another word) ────────────
_SUFFIXES = {
    "st": "Street", "ave": "Avenue", "av": "Avenue", "blvd": "Boulevard",
    "rd": "Road", "dr": "Drive", "ln": "Lane", "ct": "Court", "pl": "Place",
    "sq": "Square", "pk": "Park", "pkwy": "Parkway", "hwy": "Highway",
    "ter": "Terrace", "terr": "Terrace", "cir": "Circle", "stn": "Station",
    "sta": "Station", "ctr": "Center", "plz": "Plaza", "expy": "Expressway",
    "univ": "University", "hosp": "Hospital", "intl": "International",
}
# Prefix abbreviations (expanded at the start of a name).
_PREFIXES = {"mt": "Mount", "ft": "Fort", "st": "Saint"}

_TOKEN = re.compile(r"[A-Za-z]+\.?|[^A-Za-z]+")


def normalize_query(text: str) -> str:
    """Return a geocoder-friendly version of `text` (never empty if input isn't)."""
    raw = " ".join((text or "").split())
    if not raw:
        return raw
    cleaned = _UNIT.sub("", raw).strip(" ,")
    if not cleaned:
        cleaned = raw

    parts = _TOKEN.findall(cleaned)
    out = []
    prev_word = False
    for i, part in enumerate(parts):
        word = part.rstrip(".")
        key = word.lower()
        if word.isalpha():
            # A word is a "prefix" position when nothing word-like precedes it
            # in this comma-separated chunk.
            if not prev_word and key in _PREFIXES and i + 1 < len(parts):
                out.append(_PREFIXES[key])
            elif prev_word and key in _SUFFIXES:
                out.append(_SUFFIXES[key])
            else:
                out.append(part)
            prev_word = True
        else:
            out.append(part)
            if "," in part:
                prev_word = False
    return "".join(out).strip()


# ── Acronyms / nicknames ────────────────────────────────────────────────────
_ACRONYM = re.compile(r"^[A-Za-z]{2,6}$")


def looks_like_acronym(text: str) -> bool:
    """Short single token typed in capitals ("MIT", "NYC", "JP"), or a 2-3
    letter lowercase token ("bu"), which a geocoder can't spell-match."""
    t = (text or "").strip().rstrip(".")
    if not _ACRONYM.match(t):
        return False
    return t.isupper() or len(t) <= 3


_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_EXPAND_TIMEOUT = aiohttp.ClientTimeout(total=5.0)
_NONE_ANSWERS = {"none", "unknown", "n/a", ""}


async def expand_acronym(token: str, city: Optional[str]) -> Optional[str]:
    """Ask a fast LLM what place `token` most likely means near `city`.

    Returns the full place name, or None (no key, timeout, or unsure).
    Results, including None, are cached for a day per (token, city).
    """
    token = (token or "").strip().rstrip(".")
    if not token or not settings.GROQ_API_KEY:
        return None
    where = (city or "").strip()
    key = f"geocode.acronym:{token.lower()}:{where.lower()}"
    cached = await cache.get(key)
    if cached is not None:
        return cached or None

    context = f"someone in or near {where}" if where else "someone searching a map"
    prompt = (
        f'For {context}, what place does the abbreviation or nickname "{token}" most '
        "commonly refer to on a map? Prefer places in or near that area. It may be a "
        "university, airport, neighborhood, city, landmark or station. Reply with "
        "only the full official place name "
        f"followed by the city, e.g. \"Logan International Airport, Boston\". "
        "If you are not confident, reply NONE."
    )
    payload = {
        "model": settings.GROQ_FAST_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 400,
        "reasoning_effort": "low",
    }
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    answer: Optional[str] = None
    try:
        async with aiohttp.ClientSession(timeout=_EXPAND_TIMEOUT) as session:
            async with session.post(_GROQ_CHAT_URL, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    choices = data.get("choices") or []
                    text = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
                    text = text.strip().strip('"').splitlines()[0].strip() if text.strip() else ""
                    if text.lower().rstrip(".") not in _NONE_ANSWERS and len(text) <= 120:
                        answer = text
                else:
                    logger.warning("geocode.acronym.bad_status", status=resp.status)
                    return None  # don't cache transient failures
    except Exception as exc:  # noqa: BLE001
        logger.warning("geocode.acronym.error", error=str(exc))
        return None

    await cache.set(key, answer or "", ttl=86400)
    logger.info("geocode.acronym.expanded", token=token, city=where, expansion=answer)
    return answer
