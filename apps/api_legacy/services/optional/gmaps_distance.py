"""
Google Maps Distance Matrix API wrapper.
Primary API for Move Agent.
"""

import time
import httpx
from core.dependencies import assert_api_available
from core.config import settings
from services.metrics import metrics
from services.cache import cache_get, cache_set

class GoogleMapsDistanceMatrixService:
    REQUIRED_API = "google_maps"
    BASE_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

    async def get_distance(self, origins: str, destinations: str, mode: str = "driving") -> dict:
        assert_api_available(self.REQUIRED_API)
        
        cache_key = f"{origins}|{destinations}|{mode}"
        cached = cache_get("google_maps_distance", "global", cache_key)
        if cached is not None:
            return cached

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    self.BASE_URL,
                    params={
                        "origins": origins,
                        "destinations": destinations,
                        "mode": mode,
                        "key": settings.google_maps_api_key
                    }
                )
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    data = res.json()
                    
                    if data.get("status") != "OK":
                        metrics.record_provider_call("google_maps_distance", latency, False)
                        return {
                            "status": "error",
                            "distances": [],
                            "message": f"Google Maps API returned {data.get('status')}",
                            "_reason": "api_error"
                        }
                        
                    rows = data.get("rows", [])
                    elements = rows[0].get("elements", []) if rows else []
                    
                    distances = []
                    for e in elements:
                        if e.get("status") == "OK":
                            distances.append({
                                "distance_text": e.get("distance", {}).get("text", ""),
                                "duration_text": e.get("duration", {}).get("text", ""),
                                "distance_value": e.get("distance", {}).get("value", 0),
                                "duration_value": e.get("duration", {}).get("value", 0)
                            })
                    
                    result = {
                        "status": "success",
                        "distances": distances,
                        "explanation": f"Found {len(distances)} distance results via Google Maps."
                    }
                    metrics.record_provider_call("google_maps_distance", latency, bool(distances))
                    if result["status"] == "success":
                        cache_set("google_maps_distance", "global", cache_key, result)
                    return result
                
                metrics.record_provider_call("google_maps_distance", latency, False)
                return {
                    "status": "error",
                    "distances": [],
                    "message": f"Google Maps API returned HTTP {res.status_code}.",
                    "_reason": "http_error"
                }

        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("google_maps_distance", latency, False)
            return {"status": "error", "distances": [], "message": "Google Maps API timed out.", "_reason": "timeout"}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("google_maps_distance", latency, False)
            return {"status": "error", "distances": [], "message": f"Google Maps request failed: {str(e)}", "_reason": "exception"}
