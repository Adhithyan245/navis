"""Local knowledge: a short overview of the place (Wikipedia) plus etiquette
and handy phrases (AI-compiled, flagged as such)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional
from urllib.parse import quote

import aiohttp

from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import PlaceRef, get_json, result

logger = get_logger(__name__)

WIKI_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
VOYAGE_URL = "https://en.wikivoyage.org/api/rest_v1/page/summary/{title}"
_GROQ = "https://api.groq.com/openai/v1/chat/completions"


async def _overview(place: PlaceRef) -> Optional[Dict[str, Any]]:
    for title in filter(None, [f"{place.city}, {place.region}" if place.city and place.region else None,
                               f"{place.city}, {place.country}" if place.city and place.country else None,
                               place.city, place.country]):
        data = await get_json(WIKI_URL.format(title=quote(title.replace(" ", "_"))),
                              headers={"User-Agent": "Navis/1.0 (city companion)"})
        if data and data.get("extract") and data.get("type") != "disambiguation":
            return {"title": data.get("title"), "extract": data.get("extract"),
                    "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page")}
    return None


async def _travel_guide(place: PlaceRef) -> Optional[Dict[str, Any]]:
    """Wikivoyage's community travel guide for the place (CC BY-SA), if any."""
    for title in filter(None, [place.city, f"{place.city} ({place.region})" if place.city and place.region else None,
                               place.region, place.country]):
        data = await get_json(VOYAGE_URL.format(title=quote(title.replace(" ", "_"))),
                              headers={"User-Agent": "Navis/1.0 (city companion)"})
        if data and data.get("extract") and data.get("type") != "disambiguation":
            return {"title": data.get("title"), "extract": data.get("extract")[:600],
                    "url": ((data.get("content_urls") or {}).get("mobile") or {}).get("page")
                    or ((data.get("content_urls") or {}).get("desktop") or {}).get("page"),
                    "license": "CC BY-SA 4.0, Wikivoyage contributors"}
    return None


async def _etiquette(place: PlaceRef) -> Optional[Dict[str, Any]]:
    if not settings.GROQ_API_KEY:
        return None
    where = ", ".join(x for x in (place.city, place.region, place.country) if x)
    key = f"domain.etiquette:{where.lower()}"
    cached = await cache.get(key)
    if cached is not None:
        return cached or None
    prompt = (f"For a newcomer to {where}, give practical local etiquette and phrases. Only include things "
              "you are confident are true there. Return JSON only: "
              '{"etiquette": ["...", up to 6 short tips], "phrases": [{"phrase": "...", "meaning": "..."}, up to 6], '
              '"language": "main local language"}')
    payload = {"model": settings.GROQ_MODEL, "temperature": 0.2, "max_tokens": 2500,
               "reasoning_effort": "low", "response_format": {"type": "json_object"},
               "messages": [{"role": "user", "content": prompt}]}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(_GROQ, json=payload,
                                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json()
        raw = json.loads(body["choices"][0]["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        logger.info("domain.etiquette.unavailable", error=str(exc))
        return None
    tips = [re.sub(r"^\s*(tip|note|do|don't)\s*[:\-–]\s*", "", str(t), flags=re.I)[:200]
            for t in raw.get("etiquette") or [] if isinstance(t, str)][:6]
    phrases = [{"phrase": str(p.get("phrase"))[:80], "meaning": str(p.get("meaning"))[:120]}
               for p in raw.get("phrases") or [] if isinstance(p, dict) and p.get("phrase")][:6]
    out = {"etiquette": tips, "phrases": phrases, "language": str(raw.get("language") or "")[:40] or None,
           "generated": True}
    await cache.set(key, out, ttl=30 * 24 * 3600)
    return out


async def local_knowledge(place: PlaceRef) -> Dict[str, Any]:
    import asyncio
    overview, etiquette, guide = await asyncio.gather(_overview(place), _etiquette(place), _travel_guide(place))
    data = {"overview": overview, "culture": etiquette, "travel_guide": guide}
    if not overview and not etiquette:
        return result("unavailable", data,
                      message=f"Background on {place.label} isn't loading right now.",
                      alternatives=["Local tourist offices are great for history and customs."])
    msg = (overview or {}).get("extract", "")
    if msg:
        first = msg.split(". ")[0]
        msg = first if first.endswith(".") else f"{first}."
    else:
        msg = f"A few local customs to know in {place.label}."
    return result("ok" if overview and etiquette else "partial", data, message=msg[:280],
                  sources=[s for s, v in (("wikipedia", overview), ("wikivoyage", guide), ("ai", etiquette)) if v])
