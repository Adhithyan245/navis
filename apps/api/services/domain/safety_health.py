"""Safety & health: emergency numbers plus the nearest hospitals, pharmacies,
clinics and police."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from apps.api.services.domain.alerts import alerts_near
from apps.api.services.domain.common import PlaceRef, nearby, result
from apps.api.services.domain.country_facts import emergency_for
from apps.api.services.domain.helplines import directory

GROUPS = {
    "hospitals": "healthcare.hospital",
    "pharmacies": "healthcare.pharmacy",
    "clinics": "healthcare.clinic_or_praxis",
    "police": "service.police",
}


async def safety_health(place: PlaceRef) -> Dict[str, Any]:
    numbers = emergency_for(place.country_code)
    *lookups, live_alerts = await asyncio.gather(
        *(nearby(place, cat, radius_m=8000, limit=6) for cat in GROUPS.values()), alerts_near(place))
    lines = directory(place.country_code, place.city)
    data: Dict[str, Any] = {"emergency": numbers, "helplines": lines, "alerts": live_alerts or []}
    failed = 0
    for name, found in zip(GROUPS, lookups):
        if found is None:
            failed += 1
            found = []
        data[name] = found[:5]
    main = lines["primary"]["display"]
    msg = f"In an emergency in {place.label}, call {main}."
    urgent = [a for a in (live_alerts or []) if a["severity"] in ("extreme", "red", "severe", "orange")]
    if urgent:
        msg = f"Active alert: {urgent[0]['title']}. " + msg
    if not lines["curated_country"]:
        msg += " 112 works on most mobile phones worldwide; confirm the local number when you arrive."
    if failed == len(GROUPS):
        return result("partial", data, message=msg,
                      alternatives=["Nearby hospitals and pharmacies aren't loading right now; maps apps list them too."])
    if not any(data[g] for g in GROUPS):
        return result("partial", data, message=msg,
                      alternatives=["No hospitals or pharmacies are mapped within 8 km. The nearest town likely has them."])
    return result("ok", data, message=msg, sources=["openstreetmap"])
