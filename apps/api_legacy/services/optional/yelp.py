"""
Yelp Fusion API service — optional enrichment for Taste agent.

Activated only when YELP_API_KEY is set.
Falls back gracefully when key is missing or API fails.
Normalizes responses to the same schema as GooglePlacesService.
"""

import time
import httpx
from typing import Dict, Any
from core.config import settings
from services.cache import cache_get, cache_set
from services.metrics import metrics


class YelpService:
    REQUIRED_API = "yelp"

    BASE_URL = "https://api.yelp.com/v3/businesses/search"

    async def search_businesses(
        self,
        query: str,
        city: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        from core.dependencies import assert_api_available
        assert_api_available(self.REQUIRED_API)

        cached = cache_get("yelp", city, query)
        if cached is not None:
            return cached

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(
                    self.BASE_URL,
                    headers={"Authorization": f"Bearer {settings.yelp_api_key}"},
                    params={
                        "term": query,
                        "location": city,
                        "limit": limit,
                        "sort_by": "rating",
                    },
                )
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    businesses = res.json().get("businesses", [])
                    normalized = []
                    for b in businesses:
                        coords = b.get("coordinates", {})
                        lat = coords.get("latitude")
                        lng = coords.get("longitude")
                        if lat is None or lng is None:
                            continue
                        normalized.append({
                            "name": b.get("name"),
                            "address": ", ".join(
                                b.get("location", {}).get("display_address", [])
                            ),
                            "rating": b.get("rating", 0.0),
                            "price_level": len(b.get("price", "")) or None,  # "$" → 1, "$$" → 2
                            "open_now": not b.get("is_closed", True),
                            "location": {"lat": lat, "lng": lng},
                            "types": [c.get("alias") for c in b.get("categories", [])],
                            "source": "yelp",
                            "place_id": b.get("id"),
                        })

                    result = {
                        "status": "success" if normalized else "fallback",
                        "places": normalized,
                        "explanation": (
                            f"Found {len(normalized)} businesses via Yelp."
                            if normalized
                            else "Yelp returned no results for this query."
                        ),
                    }
                    metrics.record_provider_call("yelp", latency, bool(normalized))
                    if result["status"] == "success":
                        cache_set("yelp", city, query, result)
                    return result

                metrics.record_provider_call("yelp", latency, False)
                return {
                    "status": "error",
                    "places": [],
                    "explanation": f"Yelp API returned HTTP {res.status_code}.",
                }

        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("yelp", latency, False)
            return {"status": "error", "places": [], "explanation": "Yelp API timed out."}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("yelp", latency, False)
            return {"status": "error", "places": [], "explanation": f"Yelp request failed: {e}"}
