"""Travel & arrival: nearest airports and long-distance terminals, plus local
time and timezone."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.api.services.domain.common import PlaceRef, get_json, nearby, result

GROUPS = {
    "rail_stations": ("public_transport.train", 30_000),
    "ferry_terminals": ("public_transport.ferry", 60_000),
}
_NOT_PASSENGER = ("seaplane", "heliport", "helipad", "airfield", "glider", "military", "air base", "airstrip")


async def _airports(place: PlaceRef):
    """Passenger airports, international ones first; None if the lookup failed."""
    found = await nearby(place, "airport.international", radius_m=150_000, limit=10)
    if found is not None and not found:
        found = await nearby(place, "airport", radius_m=150_000, limit=10)
    if found is None:
        return None
    usable = [a for a in found if not any(w in a["name"].lower() for w in _NOT_PASSENGER)]
    def rank(a):
        tags = a.get("tags") or {}
        international = ("international" in a["name"].lower()
                         or str(tags.get("aerodrome:type", "")).lower() == "international"
                         or str(tags.get("aerodrome", "")).lower() == "international")
        # Airports with an IATA code have scheduled passenger flights.
        return (0 if international else 1 if tags.get("iata") else 2, a["distance_m"])

    usable.sort(key=rank)
    return usable


async def _timezone(place: PlaceRef) -> str | None:
    data = await get_json("https://api.open-meteo.com/v1/forecast",
                          params={"latitude": place.lat, "longitude": place.lon, "timezone": "auto",
                                  "forecast_days": 1, "daily": "sunrise"})
    return (data or {}).get("timezone")


async def arrival(place: PlaceRef) -> Dict[str, Any]:
    tz, airports_found, *found = await asyncio.gather(
        _timezone(place), _airports(place),
        *(nearby(place, cat, radius_m=r, limit=5) for cat, r in GROUPS.values()))
    data: Dict[str, Any] = {"timezone": tz, "airports": (airports_found or [])[:4]}
    if tz:
        try:
            data["local_time"] = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%dT%H:%M")
        except ZoneInfoNotFoundError:
            pass
    for name, hits in zip(GROUPS, found):
        data[name] = (hits or [])[:4]
    airports = data["airports"]
    if airports_found is None and all(h is None for h in found):
        return result("partial", data,
                      message=f"Arrival options for {place.label} aren't loading right now.",
                      alternatives=["Search flights or ferries to the nearest large city."])
    if airports:
        a = airports[0]
        code = (a.get("tags") or {}).get("iata")
        name = f"{a['name']} ({code})" if code and code not in a["name"] else a["name"]
        msg = f"The nearest airport is {name}, about {round(a['distance_m'] / 1000)} km away."
    elif data["ferry_terminals"]:
        msg = f"{place.label} is best reached by ferry; the nearest terminal is {data['ferry_terminals'][0]['name']}."
    else:
        msg = (f"There's no airport within 150 km of {place.label}. The usual route is a flight to the "
               "nearest city, then road or rail.")
    return result("ok", data, message=msg, sources=["openstreetmap"])
