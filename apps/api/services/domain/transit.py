"""Getting around: nearby stations and stops by mode, plus the local transit
card/app tip from the place guide."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from apps.api.services.domain.bikeshare import bikeshare_near
from apps.api.services.domain.common import PlaceRef, nearby, result

MODES = {
    "subway": "public_transport.subway",
    "train": "public_transport.train",
    "tram": "public_transport.tram",
    "bus": "public_transport.bus",
    "ferry": "public_transport.ferry",
}


async def transit(place: PlaceRef, *, local_tip: Optional[str] = None) -> Dict[str, Any]:
    *lookups, bikes = await asyncio.gather(
        *(nearby(place, cat, radius_m=3000, limit=8) for cat in MODES.values()), bikeshare_near(place))
    data: Dict[str, Any] = {"tip": local_tip, "bikeshare": bikes}
    available: List[str] = []
    failed = 0
    for mode, found in zip(MODES, lookups):
        if found is None:
            failed += 1
            found = []
        data[mode] = found[:5]
        if found:
            available.append(mode)
    if failed == len(MODES):
        return result("unavailable", data,
                      message=f"Transit details for {place.label} aren't loading right now.",
                      alternatives=["Maps apps show live routes and stops."])
    if not available and not bikes:
        return result("empty", data,
                      message=f"Public transit is limited around {place.label}. Walking, cycling, taxis "
                              "or rideshare are the usual ways to get around.",
                      alternatives=["Ask your accommodation about local shuttles or ferries."])
    names = {"subway": "metro", "train": "train", "tram": "tram", "bus": "bus", "ferry": "ferry"}
    options = [names[m] for m in available] + ([f"{bikes['network']} bike share"] if bikes else [])
    return result("ok", data,
                  message=f"Nearby you'll find {', '.join(options)} options.",
                  sources=["openstreetmap"])
