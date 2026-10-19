"""
Health & emergency services for a place:

  * emergency + helpline directory (curated, see helplines.py)
  * nearby care: hospitals, clinics, dentists, pharmacies — with phone,
    website, opening hours and distance (OpenStreetMap via Geoapify)
  * where to book: the country's real appointment / telehealth platforms
  * official city websites for uncurated cities (AI-suggested, link-checked,
    flagged `generated`). No AI phone numbers: every number shown is curated.

Booking happens on the provider's own site or by phone; Navis links there
and says so. It does not create appointments itself.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

import aiohttp

from apps.api.core.netguard import safe_status
from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.common import PlaceRef, nearby, result
from apps.api.services.domain.helplines import directory

logger = get_logger(__name__)

FACILITY_KINDS: Dict[str, Dict[str, Any]] = {
    "hospitals": {"category": "healthcare.hospital", "label": "Hospitals & emergency rooms", "radius": 15000},
    "clinics": {"category": "healthcare.clinic_or_praxis", "label": "Clinics & doctors", "radius": 6000},
    "dentists": {"category": "healthcare.dentist", "label": "Dentists", "radius": 6000},
    "pharmacies": {"category": "healthcare.pharmacy", "label": "Pharmacies", "radius": 4000},
}

# Appointment / telehealth platforms that genuinely operate in each country.
BOOKING: Dict[str, List[Dict[str, str]]] = {
    "US": [
        {"name": "Zocdoc", "url": "https://www.zocdoc.com", "what": "Book in-person doctors and dentists"},
        {"name": "Teladoc", "url": "https://www.teladoc.com", "what": "24/7 video visits"},
        {"name": "Amwell", "url": "https://amwell.com", "what": "Video visits with US clinicians"},
    ],
    "IN": [
        {"name": "eSanjeevani", "url": "https://esanjeevani.mohfw.gov.in", "what": "Free government teleconsultation"},
        {"name": "Practo", "url": "https://www.practo.com", "what": "Book doctors, clinics and video consults"},
        {"name": "Apollo 24|7", "url": "https://www.apollo247.com", "what": "Doctor consults, pharmacy delivery"},
    ],
    "GB": [
        {"name": "NHS App", "url": "https://www.nhs.uk/nhs-app/", "what": "Book GP appointments, repeat prescriptions"},
        {"name": "NHS 111 online", "url": "https://111.nhs.uk", "what": "Urgent advice and where to go"},
    ],
    "CA": [{"name": "Health811 / provincial lines", "url": "https://www.canada.ca/en/health-canada.html", "what": "Nurse advice and where to get care"}],
    "AU": [
        {"name": "HotDoc", "url": "https://www.hotdoc.com.au", "what": "Book GPs and specialists"},
        {"name": "healthdirect", "url": "https://www.healthdirect.gov.au", "what": "Symptom checker and service finder"},
    ],
    "DE": [{"name": "Doctolib", "url": "https://www.doctolib.de", "what": "Book doctors and video consults"}],
    "FR": [{"name": "Doctolib", "url": "https://www.doctolib.fr", "what": "Book doctors and video consults"}],
    "IT": [{"name": "MioDottore", "url": "https://www.miodottore.it", "what": "Book doctors and specialists"}],
    "ES": [{"name": "Doctoralia", "url": "https://www.doctoralia.es", "what": "Book doctors and specialists"}],
    "SG": [{"name": "HealthHub", "url": "https://www.healthhub.sg", "what": "Book polyclinic appointments"}],
    "IS": [{"name": "Heilsuvera", "url": "https://www.heilsuvera.is", "what": "Health centre bookings and advice"}],
}

_GROQ = "https://api.groq.com/openai/v1/chat/completions"


def _facility(p: Dict[str, Any]) -> Dict[str, Any]:
    website = p.get("website")
    if website and not str(website).startswith(("http://", "https://")):
        website = f"https://{website}"
    return {
        "name": p.get("name"),
        "address": p.get("address"),
        "distance_m": p.get("distance_m"),
        "lat": p.get("lat"),
        "lon": p.get("lon"),
        "phone": p.get("phone"),
        "website": website,
        "opening_hours": p.get("opening_hours"),
        "emergency": "emergency" in " ".join(p.get("categories") or []),
    }


async def _link_ok(session: aiohttp.ClientSession, url: str) -> bool:
    # Model-suggested URLs: only public hosts, every redirect hop re-checked.
    status = await safe_status(session, url, method="GET")
    return status is not None and (status < 400 or status in (401, 403, 405, 429))  # exists, just guarded


async def city_resources(place: PlaceRef) -> Optional[List[Dict[str, Any]]]:
    """For cities without curated lines: official websites (city hall,
    tourist board, public transport, utilities) suggested by the model and
    kept only if the link actually loads. No phone numbers: unverifiable
    numbers are too risky to show. Cached 30 days."""
    if not settings.GROQ_API_KEY or not place.city:
        return None
    where = ", ".join(x for x in (place.city, place.region, place.country) if x)
    key = f"care.cityresources:{where.lower()}"
    cached = await cache.get(key)
    if cached is not None:
        return cached or None
    prompt = (
        f"List up to 5 OFFICIAL websites a newcomer to {where} would use for local services: the city "
        "or municipal government, the official tourist board, the public transport operator, and "
        "water/electricity providers. Homepages only, no deep links. Only include sites you are sure "
        'exist. Return JSON only: {"sites": [{"name": "...", "url": "https://...", '
        '"category": "city|tourist|transit|utilities"}]}'
    )
    payload = {"model": settings.GROQ_MODEL, "temperature": 0, "max_tokens": 2000,
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
            candidates = []
            for row in raw.get("sites") or []:
                if not isinstance(row, dict):
                    continue
                url = str(row.get("url") or "").strip()
                category = str(row.get("category") or "city").lower()
                if re.match(r"^https://[^\s/]+\.[^\s]{2,}$", url) and category in ("city", "tourist", "transit", "utilities"):
                    candidates.append({"name": str(row.get("name") or "Official site")[:80], "url": url,
                                       "category": category, "generated": True})
            checks = await asyncio.gather(*(_link_ok(session, c["url"]) for c in candidates[:5]))
    except Exception as exc:  # noqa: BLE001
        logger.info("care.cityresources.unavailable", error=str(exc))
        return None
    sites = [c for c, ok in zip(candidates, checks) if ok]
    await cache.set(key, sites, ttl=30 * 24 * 3600)
    return sites or None


async def care(place: PlaceRef, *, include_generated: bool = True) -> Dict[str, Any]:
    lines = directory(place.country_code, place.city)
    kinds = list(FACILITY_KINDS)
    lookups = await asyncio.gather(
        *(nearby(place, FACILITY_KINDS[k]["category"], radius_m=FACILITY_KINDS[k]["radius"], limit=12) for k in kinds),
        city_resources(place) if include_generated and not lines["curated_city"] else asyncio.sleep(0, None),
    )
    *facility_lists, generated = lookups
    facilities = {}
    failed = 0
    for k, found in zip(kinds, facility_lists):
        if found is None:
            failed += 1
        facilities[k] = {"label": FACILITY_KINDS[k]["label"], "items": [_facility(p) for p in (found or [])[:10]]}
    data = {
        "emergency": lines["primary"],
        "helplines": {"national": lines["national"], "city": lines["city"]},
        # Official city websites (AI-suggested, link-checked) where we have
        # no curated city lines.
        "city_resources": generated or [],
        "facilities": facilities,
        "booking": BOOKING.get((place.country_code or "").upper(), []),
        "curated_country": lines["curated_country"],
    }
    primary = lines["primary"]
    msg = f"In an emergency in {place.label}, call {primary['display']}."
    if not lines["curated_country"]:
        msg += " Confirm the local number when you arrive."
    if failed == len(kinds):
        return result("partial", data, message=msg,
                      alternatives=["Nearby hospitals and pharmacies aren't loading right now; maps apps list them too."])
    if not any(f["items"] for f in facilities.values()):
        return result("partial", data, message=msg,
                      alternatives=[f"No hospitals or clinics are mapped close to {place.label}. "
                                    "The nearest larger town will have them."])
    return result("ok", data, message=msg, sources=["openstreetmap"])
