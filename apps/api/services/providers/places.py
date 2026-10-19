from typing import Optional
import aiohttp
from apps.api.services.providers.base import BaseProvider
from apps.api.observability.circuit_breaker import circuit_breaker
from apps.api.services.cache.ttl_cache import ttl_cache
from apps.api.core.config import settings

PLACES_LIMIT = 20

# Foursquare retired api.foursquare.com/v3 for new keys; the Places API now
# lives here, takes a Bearer service key and requires a version header.
FOURSQUARE_SEARCH_URL = "https://places-api.foursquare.com/places/search"
FOURSQUARE_API_VERSION = "2025-06-17"

# category → Foursquare free-text query
_FOURSQUARE_QUERIES = {
    "dining": "restaurant",
    "cafe": "coffee",
    "bar": "bar",
    "bakery": "bakery",
}

# category → Geoapify category list
_GEOAPIFY_CATEGORIES = {
    "dining": "catering.restaurant",
    "cafe": "catering.cafe",
    "bar": "catering.bar,catering.pub",
    "bakery": "commercial.food_and_drink.bakery",
}

# Query keywords that narrow a workflow's default category, so "coffee
# shops near X" returns cafes rather than the workflow's fixed `dining`.
_QUERY_CATEGORY_HINTS = (
    (("coffee", "cafe", "café", "espresso", "tea house"), "cafe"),
    (("bakery", "bakeries", "pastry"), "bakery"),
    (("bar ", "bars", "pub", "pubs", "brewery", "cocktail"), "bar"),
)


def infer_category(category: str, query: Optional[str]) -> str:
    text = f" {(query or '').lower()} "
    for keywords, hinted in _QUERY_CATEGORY_HINTS:
        if any(k in text for k in keywords):
            return hinted
    return category


def foursquare_to_feature(place: dict) -> dict:
    """Reshape a Foursquare place into the GeoJSON Feature shape Geoapify
    returns, so fusion, ranking and the frontend see one format."""
    lat, lon = place.get("latitude"), place.get("longitude")
    loc = place.get("location") or {}
    categories = [c.get("name") for c in place.get("categories") or [] if c.get("name")]
    fsq_id = place.get("fsq_place_id")
    props = {
        "name": place.get("name"),
        "place_id": f"fsq:{fsq_id}" if fsq_id else None,
        "lat": lat,
        "lon": lon,
        "formatted": loc.get("formatted_address"),
        "address_line1": place.get("name"),
        "address_line2": loc.get("formatted_address"),
        "street": loc.get("address"),
        "city": loc.get("locality"),
        "postcode": loc.get("postcode"),
        "categories": categories,
        "distance": place.get("distance"),
        "website": place.get("website"),
        "phone": place.get("tel"),
        "datasource": {"sourcename": "foursquare"},
    }
    feature = {"type": "Feature",
               "properties": {k: v for k, v in props.items() if v not in (None, "", [])}}
    if lat is not None and lon is not None:
        feature["geometry"] = {"type": "Point", "coordinates": [lon, lat]}
    return feature


class PlacesProvider(BaseProvider):
    @ttl_cache(ttl=3600)
    @circuit_breaker(threshold=3, timeout=30)
    async def fetch(self, lat: float, lon: float, category: str = "dining",
                    query: Optional[str] = None) -> list:
        category = infer_category(category, query)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12, connect=5)) as session:
            # Foursquare Primary
            if settings.FOURSQUARE_API_KEY:
                params = {
                    "ll": f"{lat},{lon}",
                    "query": _FOURSQUARE_QUERIES.get(category, category),
                    "limit": PLACES_LIMIT,
                    "sort": "DISTANCE",
                    "radius": 5000,
                }
                headers = {
                    "Authorization": f"Bearer {settings.FOURSQUARE_API_KEY}",
                    "X-Places-Api-Version": FOURSQUARE_API_VERSION,
                    "Accept": "application/json",
                }
                async with session.get(FOURSQUARE_SEARCH_URL, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results") or []
                        if results:
                            return [foursquare_to_feature(r) for r in results]

            # Geoapify Fallback
            if settings.GEOAPIFY_API_KEY:
                g_cat = _GEOAPIFY_CATEGORIES.get(category, "commercial")
                # bias=proximity sorts by distance from the anchor; without it
                # Geoapify returns arbitrary matches anywhere in the circle.
                geoapify_url = (
                    f"https://api.geoapify.com/v2/places?categories={g_cat}"
                    f"&filter=circle:{lon},{lat},5000&bias=proximity:{lon},{lat}"
                    f"&limit={PLACES_LIMIT}&apiKey={settings.GEOAPIFY_API_KEY}"
                )
                async with session.get(geoapify_url) as fb_resp:
                    if fb_resp.status == 200:
                        data = await fb_resp.json()
                        return data.get("features", [])

        raise ValueError("Places APIs failed or keys are missing.")
