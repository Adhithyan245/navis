"""
routes/geocode.py — universal location resolution endpoints.

Thin HTTP surface over GeocodingService (Geoapify primary, Nominatim
fallback). The frontend LocationSearch component calls these to resolve any
city / neighborhood / street / postcode / landmark / address / coordinate
worldwide into canonical Location objects.

These are additive Phase 3A endpoints; existing routes are unchanged.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query

from apps.api.models.location import Location
from apps.api.services.geocoding import geocoding_service

router = APIRouter(prefix="/v2/geocode", tags=["Geocoding"])


@router.get("/search")
async def geocode_search(
    text: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(5, ge=1, le=10),
    autocomplete: bool = Query(False),
    bias_lat: Optional[float] = Query(None, ge=-90, le=90),
    bias_lon: Optional[float] = Query(None, ge=-180, le=180),
    city: Optional[str] = Query(None, max_length=80),
) -> dict:
    """Resolve free text or a 'lat,lon' coordinate into ranked Locations.

    `bias_lat`/`bias_lon` (usually the user's city centre) rank nearby
    matches first; `city` is context for expanding acronyms like "NEU"."""
    results: List[Location] = await geocoding_service.search(
        text, limit=limit, autocomplete=autocomplete,
        bias_lat=bias_lat, bias_lon=bias_lon, city=city,
    )
    return {"results": [r.model_dump() for r in results]}


@router.get("/reverse")
async def geocode_reverse(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict:
    """Resolve a coordinate into the nearest canonical Location."""
    result: Optional[Location] = await geocoding_service.reverse(lat, lon)
    return {"result": result.model_dump() if result else None}
