"""
routes/events.py — events near a place, worldwide.

  GET /v2/events          search (location + optional category/dates/keyword)
  GET /v2/events/{id}     full detail for one event

Location comes from the client (usually the user's city Location: lat/lon,
city, country_code). When country_code is missing it's resolved by reverse
geocoding so holidays and local tech conferences still work.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from apps.api.services.events_service import CATEGORIES, events_service
from apps.api.services.geocoding import geocoding_service

router = APIRouter(prefix="/v2/events", tags=["Events"])


@router.get("")
async def search_events(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    city: Optional[str] = Query(None, max_length=120),
    country_code: Optional[str] = Query(None, min_length=2, max_length=2),
    country: Optional[str] = Query(None, max_length=80),
    region: Optional[str] = Query(None, max_length=80),
    category: Optional[str] = Query(None, description=f"One of: {', '.join(CATEGORIES)}"),
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    keyword: Optional[str] = Query(None, max_length=80),
) -> dict:
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category. Use one of: {', '.join(CATEGORIES)}")
    if not country_code or not city:
        place = await geocoding_service.reverse(lat, lon)
        if place:
            country_code = country_code or place.country_code
            country = country or place.country
            city = city or place.city or place.name
            region = region or place.region
    return await events_service.search(
        lat=lat, lon=lon, city=city, country_code=country_code, country=country,
        category=category, date_from=date_from, date_to=date_to, keyword=keyword,
        region=region,
    )


@router.get("/{event_id}")
async def event_detail(event_id: str) -> dict:
    if not event_id or len(event_id) > 200:
        raise HTTPException(status_code=404, detail="Event not found.")
    event = await events_service.detail(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")
    return {"event": event}
