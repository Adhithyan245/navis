"""
PlaceGuide — place-specific relocation essentials for places with no
hand-written corpus (everything except the cities under knowledge/cities).

Asks the LLM for a structured JSON list of the things a newcomer to that
exact place has to sort out (local transit card, SIM/eSIM, emergency
numbers, residency registration, banking, healthcare, utilities, safety,
etiquette...), validates and clamps it, and returns items in the same
"chunk view" shape the markdown corpus produces, so the plan and essentials
pages render them unchanged.

Cached on disk per place (country code + city) for 30 days, with one
generation in flight per place. Never raises: returns [] when the LLM is
unavailable, and callers fall back to the universal corpus.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from apps.api.core.netguard import safe_status
from apps.api.core.config import settings
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT = aiohttp.ClientTimeout(total=60)
_TTL_S = 30 * 24 * 3600
_MAX_ITEMS = 16
_GUIDE_VERSION = 2  # bump to regenerate cached guides

STAGES = ("pre_arrival", "week_1", "month_1", "month_3")
URGENCIES = ("high", "medium", "low")
_TOPICS = (
    "transit", "phone", "emergency", "registration", "visa", "banking", "healthcare",
    "housing", "utilities", "safety", "etiquette", "money", "driving", "tax", "food",
    "community", "documents", "education", "work", "other",
)

_locks: Dict[str, asyncio.Lock] = {}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60] or "place"


def place_key(city: str, country_code: Optional[str]) -> str:
    return f"{(country_code or 'xx').lower()}-{_slug(city)}"


def _cache_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "place_guides"


def _cache_path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def _read_cache(key: str) -> Optional[List[Dict[str, Any]]]:
    path = _cache_path(key)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("version") != _GUIDE_VERSION or time.time() - data.get("created_at", 0) > _TTL_S:
        return None
    items = data.get("items")
    return items if isinstance(items, list) and items else None


def _write_cache(key: str, place: Dict[str, Any], items: List[Dict[str, Any]]) -> None:
    try:
        _cache_dir().mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(
            json.dumps({"version": _GUIDE_VERSION, "created_at": time.time(),
                        "place": place, "items": items}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("place_guide.cache_write_failed", error=str(exc))


def _prompt(city: str, region: Optional[str], country: Optional[str], exclude: List[str]) -> str:
    where = ", ".join(x for x in (city, region, country) if x)
    skip = "; ".join(exclude[:12])
    return f"""You help people who have just moved to, or are about to move to: {where}.

List the {_MAX_ITEMS - 4} to {_MAX_ITEMS} most important practical things a newcomer must sort out THERE,
specific to that exact place: the actual name of the local transit card or app, the local
emergency numbers, how SIM/eSIM works there and the main carriers, residency or address
registration rules, how to open a bank account or what payment apps locals use, how to
register with healthcare, utilities, safety tips, tipping and etiquette, and anything unusual
about this place (ferries for islands, seasonal weather, altitude, permits).

Generic items already covered elsewhere (do NOT repeat them): {skip or "none"}.

Rules:
- Only include facts you are confident are true for {where}. Never invent product, app, card,
  carrier or agency names: if unsure of a name, describe it generically ("the city bus card").
  Never borrow names from neighbouring countries.
- "official_url": the official homepage only (e.g. https://www.example.gov), never a guessed
  deep link. Use null when unsure. Links are checked and broken ones removed.
- Return ONLY a JSON object of this shape:
{{"items": [{{
  "title": "imperative, under 80 chars, e.g. 'Get a Strætó Klapp card for buses'",
  "detail": "2-3 sentences of concrete how-to",
  "urgency": "high|medium|low",
  "stage": "pre_arrival|week_1|month_1|month_3",
  "topic": "{'|'.join(_TOPICS)}",
  "official_url": "https://... or null"
}}]}}"""


def _review_prompt(where: str, draft: Any) -> str:
    return f"""Below is a draft newcomer checklist for {where}, as JSON.

Fact-check it for {where} specifically:
- If an item names a card, app, carrier, bank, agency, law or number that belongs to a
  DIFFERENT country or city, or that you are not confident exists in {where}, rewrite it
  generically (e.g. "Get the local bus card") or correct it if you are sure.
- Remove duplicates and anything not useful to a newcomer.
- Keep the same JSON shape and fields. Set official_url to null if you are not sure it is
  the official homepage.

Return ONLY the corrected JSON object.

{json.dumps(draft, ensure_ascii=False)}"""


def _clean_items(raw: Any, *, city: str, key: str) -> List[Dict[str, Any]]:
    """Validate/clamp the model's JSON into chunk views. Drops bad rows."""
    rows = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    seen = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        title = " ".join(str(row.get("title") or "").split())[:120]
        if len(title) < 4 or title.lower() in seen:
            continue
        seen.add(title.lower())
        detail = " ".join(str(row.get("detail") or "").split())[:600]
        urgency = str(row.get("urgency") or "medium").lower()
        urgency = urgency if urgency in URGENCIES else "medium"
        stage = str(row.get("stage") or "week_1").lower()
        stage = stage if stage in STAGES else "week_1"
        topic = str(row.get("topic") or "other").lower()
        topic = topic if topic in _TOPICS else "other"
        url = row.get("official_url")
        url = url.strip() if isinstance(url, str) and re.match(r"^https://[^\s]{4,200}$", url.strip()) else None
        item_id = f"{key}-{_slug(title)[:40]}"
        frontmatter = {
            "id": item_id,
            "title": title,
            "urgency": urgency,
            "stage": stage,
            "household": "any",
            "city": city.lower(),
            "tags": ["essentials", "checklist", "relocation", "plan", topic],
            "generated": True,
        }
        if url:
            frontmatter["external_link"] = url
        out.append({
            "path": f"generated/{key}/{i}",
            "city": city.lower(),
            "workflow": None,
            "tags": sorted(frontmatter["tags"]),
            "priority": {"high": 3, "medium": 2, "low": 1}[urgency],
            "body": detail,
            "frontmatter": frontmatter,
        })
        if len(out) >= _MAX_ITEMS:
            break
    return out


async def _ask_llm(prompt: str) -> Optional[Any]:
    """JSON answer from the main model; on rate limiting, wait (per
    Retry-After, capped) and fall back to the fast model."""
    if not settings.GROQ_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    attempts = (settings.GROQ_MODEL, settings.GROQ_MODEL, settings.GROQ_FAST_MODEL)
    data = None
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        for attempt, model in enumerate(attempts):
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "reasoning_effort": "medium",
                "max_tokens": 6000,
            }
            try:
                async with session.post(_GROQ_CHAT_URL, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        break
                    logger.warning("place_guide.llm_bad_status", status=resp.status, model=model)
                    if resp.status not in (429, 500, 502, 503) or attempt == len(attempts) - 1:
                        return None
                    try:
                        wait = float(resp.headers.get("retry-after") or 2)
                    except ValueError:
                        wait = 2.0
            except Exception as exc:  # noqa: BLE001
                logger.warning("place_guide.llm_error", error=str(exc), model=model)
                wait = 1.0
            await asyncio.sleep(min(max(wait, 0.5), 10.0))
    if data is None:
        return None
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    try:
        return json.loads(content)
    except ValueError:
        # Tolerate a fenced or prefixed answer.
        m = re.search(r"\{.*\}", content, re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except ValueError:
            return None


async def _link_ok(session: aiohttp.ClientSession, url: str) -> bool:
    # Model-suggested URLs: only public hosts, every redirect hop re-checked.
    status = await safe_status(session, url, method="GET")
    return status is not None and (status < 400 or status in (401, 403, 405, 429))  # exists, just guarded


async def _drop_dead_links(items: List[Dict[str, Any]]) -> None:
    """Remove external links that don't resolve (models guess deep links)."""
    with_links = [i for i in items if i["frontmatter"].get("external_link")]
    if not with_links:
        return
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = await asyncio.gather(
            *(_link_ok(session, i["frontmatter"]["external_link"]) for i in with_links))
    for item, ok in zip(with_links, results):
        if not ok:
            item["frontmatter"].pop("external_link", None)


async def guide_for(
    city: str,
    *,
    country_code: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    exclude_titles: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Place-specific essentials as chunk views (possibly cached). Never raises."""
    city = (city or "").strip()
    if not city:
        return []
    key = place_key(city, country_code)
    cached = _read_cache(key)
    if cached is not None:
        return cached

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _read_cache(key)  # another request may have just filled it
        if cached is not None:
            return cached
        started = time.monotonic()
        raw = await _ask_llm(_prompt(city, region, country, exclude_titles or []))
        if raw is not None:
            # Second pass: the model checks its own list against this exact
            # place (catches names borrowed from neighbouring countries).
            where = ", ".join(x for x in (city, region, country) if x)
            reviewed = await _ask_llm(_review_prompt(where, raw))
            if reviewed is not None and _clean_items(reviewed, city=city, key=key):
                raw = reviewed
        items = _clean_items(raw, city=city, key=key) if raw is not None else []
        if items:
            await _drop_dead_links(items)
        logger.info("place_guide.generated", place=key, items=len(items),
                    seconds=round(time.monotonic() - started, 1))
        if items:
            _write_cache(key, {"city": city, "region": region, "country": country,
                               "country_code": country_code}, items)
        return items
