"""
Google Maps Directions API wrapper.
Primary API for Transit Agent.
"""

import time
import httpx
from core.dependencies import assert_api_available
from core.config import settings
from services.metrics import metrics
from services.cache import cache_get, cache_set

class GoogleMapsDirectionsService:
    REQUIRED_API = "google_maps"
    BASE_URL = "https://maps.googleapis.com/maps/api/directions/json"

    async def get_directions(self, origin: str, destination: str, mode: str = "transit") -> dict:
        assert_api_available(self.REQUIRED_API)
        
        cache_key = f"{origin}|{destination}|{mode}"
        cached = cache_get("google_maps_directions", "global", cache_key)
        if cached is not None:
            return cached

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    self.BASE_URL,
                    params={
                        "origin": origin,
                        "destination": destination,
                        "mode": mode,
                        "key": settings.google_maps_api_key
                    }
                )
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    data = res.json()
                    
                    if data.get("status") != "OK":
                        metrics.record_provider_call("google_maps_directions", latency, False)
                        return {
                            "status": "error",
                            "routes": [],
                            "message": f"Google Maps API returned {data.get('status')}",
                            "_reason": "api_error"
                        }
                        
                    routes = data.get("routes", [])
                    parsed_routes = []
                    
                    for r in routes:
                        legs = r.get("legs", [])
                        if not legs: continue
                        leg = legs[0]
                        parsed_routes.append({
                            "summary": r.get("summary", "Route"),
                            "distance": leg.get("distance", {}).get("text", ""),
                            "duration": leg.get("duration", {}).get("text", ""),
                            "steps": [s.get("html_instructions", "") for s in leg.get("steps", [])]
                        })
                    
                    result = {
                        "status": "success",
                        "routes": parsed_routes,
                        "stops": [],
                        "alerts": [],
                        "explanation": f"Found {len(parsed_routes)} routes via Google Maps."
                    }
                    metrics.record_provider_call("google_maps_directions", latency, bool(parsed_routes))
                    if result["status"] == "success":
                        cache_set("google_maps_directions", "global", cache_key, result)
                    return result
                
                metrics.record_provider_call("google_maps_directions", latency, False)
                return {
                    "status": "error",
                    "routes": [],
                    "message": f"Google Maps API returned HTTP {res.status_code}.",
                    "_reason": "http_error"
                }

        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("google_maps_directions", latency, False)
            return {"status": "error", "routes": [], "message": "Google Maps API timed out.", "_reason": "timeout"}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("google_maps_directions", latency, False)
            return {"status": "error", "routes": [], "message": f"Google Maps request failed: {str(e)}", "_reason": "exception"}
