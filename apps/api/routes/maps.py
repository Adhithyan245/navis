"""
routes/maps.py — the map experience and health & emergency services.

  GET /v2/maps/categories            quick-filter list for the map
  GET /v2/maps/nearby                places of one category around a point
  GET /v2/maps/route                 directions (geometry + steps) by mode
  GET /v2/maps/place                 details for a shop/landmark tapped on the map
  GET /v2/transit/live/boards        live departure boards for the nearest stops
  GET /v2/transit/live/departures    live departures at one stop
  GET /v2/transit/live/vehicles      vehicles moving through a map area (animated on the map)
  GET /v2/transit/live/trip          track one vehicle: position, stops ahead, ETA at your stop
  GET /v2/care                      emergency numbers, helplines, nearby
                                     care and where to book, for a place
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from apps.api.services.domain.care import care
from apps.api.services.domain.common import PlaceRef
from apps.api.services.domain import live_transit
from apps.api.services.domain.maps import CATEGORIES, MODES, directions, place_details, places_by_category
from apps.api.services.geocoding import geocoding_service

router = APIRouter(tags=["Maps & care"])


@router.get("/v2/maps/categories")
async def map_categories() -> dict:
    return {"categories": [{"key": k, "label": v["label"]} for k, v in CATEGORIES.items()]}


@router.get("/v2/maps/nearby")
async def map_nearby(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    category: str = Query(..., max_length=40),
    radius_m: int = Query(3000, ge=200, le=50000),
) -> dict:
    if category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown category.")
    return await places_by_category(PlaceRef(lat=lat, lon=lon), category, radius_m=radius_m)


@router.get("/v2/maps/route")
async def map_route(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lon: float = Query(..., ge=-180, le=180),
    modes: str = Query("drive,walk,bike,transit", max_length=60),
) -> dict:
    wanted = [m.strip() for m in modes.split(",") if m.strip() in MODES]
    return await directions((from_lat, from_lon), (to_lat, to_lon), wanted)


@router.get("/v2/maps/place")
async def map_place(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    name: str = Query("", max_length=160),
) -> dict:
    return await place_details(lat, lon, name.strip())


@router.get("/v2/transit/live/boards")
async def live_boards(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    stops: int = Query(3, ge=1, le=6),
) -> dict:
    return await live_transit.nearby_boards(lat, lon, stops=stops)


@router.get("/v2/transit/live/departures")
async def live_departures(stop_id: str = Query(..., min_length=1, max_length=200),
                          n: int = Query(10, ge=1, le=30)) -> dict:
    board = await live_transit.departures(stop_id, n=n)
    if board is None:
        return {"stop_id": stop_id, "departures": [], "message": "Live departures aren't loading right now."}
    return board


@router.get("/v2/transit/live/trip")
async def live_trip(trip_id: str = Query(..., min_length=1, max_length=300),
                    stop_id: Optional[str] = Query(None, max_length=300),
                    stop_name: Optional[str] = Query(None, max_length=200),
                    at: Optional[str] = Query(None, max_length=40)) -> dict:
    found = await live_transit.trip(trip_id, stop_id=stop_id or None, stop_name=stop_name or None, at=at or None)
    if found is None:
        return {"trip_id": trip_id, "stops": [], "vehicle": None, "path": [], "your_stop": None,
                "message": "We can't find this trip right now. It may have finished, or live data is unavailable."}
    return found


@router.get("/v2/transit/live/vehicles")
async def live_vehicles(
    min_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lat: float = Query(..., ge=-90, le=90),
    max_lon: float = Query(..., ge=-180, le=180),
    zoom: float = Query(14, ge=0, le=22),
) -> dict:
    if max_lat <= min_lat or max_lon <= min_lon:
        raise HTTPException(status_code=422, detail="Invalid area.")
    return await live_transit.vehicles(min_lat, min_lon, max_lat, max_lon, zoom=zoom)


@router.get("/v2/care")
async def care_services(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    city: Optional[str] = Query(None, max_length=120),
    country_code: Optional[str] = Query(None, min_length=2, max_length=2),
    country: Optional[str] = Query(None, max_length=80),
    region: Optional[str] = Query(None, max_length=80),
) -> dict:
    if not country_code or not city:
        place = await geocoding_service.reverse(lat, lon)
        if place:
            country_code = country_code or place.country_code
            country = country or place.country
            city = city or place.city or place.name
            region = region or place.region
    return await care(PlaceRef(lat=lat, lon=lon, city=city, country=country,
                               country_code=country_code, region=region))
