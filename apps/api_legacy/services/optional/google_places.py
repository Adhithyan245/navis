import os
from core.dependencies import assert_api_available
import time
import httpx
from typing import Dict, Any, List
from services.cache import cache_get, cache_set
from services.metrics import metrics

class GooglePlacesService:
    REQUIRED_API = "google_places"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.base_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    async def search_places(self, query: str, location: str, neighborhood: str = "") -> Dict[str, Any]:
        from core.dependencies import assert_api_available
        assert_api_available(self.REQUIRED_API)

        full_query = f"{query} in {neighborhood}, {location}" if neighborhood else f"{query} in {location}"

        # Check cache
        cached = cache_get("google_places", location, full_query)
        if cached is not None:
            return cached

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.base_url,
                    params={"query": full_query, "key": self.api_key},
                )
                latency = (time.time() - t0) * 1000
                response.raise_for_status()
                data = response.json()

                if data.get("status") not in ["OK", "ZERO_RESULTS"]:
                    metrics.record_provider_call("google_places", latency, False)
                    return {
                        "status": "error",
                        "places": [],
                        "explanation": f"Google Places API error: {data.get('status')} - {data.get('error_message', '')}"
                    }

                results = data.get("results", [])
                normalized = []
                for place in results:
                    loc = place.get("geometry", {}).get("location", {})
                    if not loc.get("lat"):
                        continue  # Skip places without coordinates

                    normalized.append({
                        "name": place.get("name"),
                        "address": place.get("formatted_address"),
                        "rating": place.get("rating", 0.0),
                        "price_level": place.get("price_level"),  # int 0-4 or None
                        "open_now": place.get("opening_hours", {}).get("open_now") if isinstance(place.get("opening_hours"), dict) else None,
                        "location": loc,
                        "types": place.get("types", []),
                        "source": "google_places",
                        "place_id": place.get("place_id")
                    })

                result = {
                    "status": "success" if normalized else "fallback",
                    "places": normalized,
                    "explanation": f"Found {len(normalized)} places." if normalized else "No places found."
                }
                metrics.record_provider_call("google_places", latency, bool(normalized))
                if result["status"] == "success":
                    cache_set("google_places", location, full_query, result)
                return result

        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("google_places", latency, False)
            return {"status": "error", "places": [], "explanation": "Google Places API timeout."}
        except httpx.HTTPStatusError as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("google_places", latency, False)
            return {"status": "error", "places": [], "explanation": f"Google Places API HTTP error: {e.response.status_code}"}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("google_places", latency, False)
            return {"status": "error", "places": [], "explanation": f"Google Places API unexpected error: {str(e)}"}
