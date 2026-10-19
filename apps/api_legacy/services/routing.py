import time
import httpx
import asyncio
from typing import Dict, Any, Optional
from services.cache import cache_get, cache_set
from services.metrics import metrics
from services.provider_base import BaseProvider, ProviderCapability, registry
import logging

logger = logging.getLogger(__name__)

class OSRMProvider(BaseProvider):
    def __init__(self):
        self.url_base = "https://router.project-osrm.org/route/v1"
        self._capability = ProviderCapability(
            id="osrm_routing",
            name="OSRM Routing API",
            is_primary=True,
            requires_key=False,
            domains=["routing", "transit", "move"]
        )

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    async def _make_request(self, profile: str, coords: str, retries: int = 2) -> Optional[dict]:
        url = f"{self.url_base}/{profile}/{coords}"
        params = {
            "overview": "full",
            "geometries": "geojson"
        }
        headers = {
            "User-Agent": "NavisOpenInfraBot/1.0 (navis@example.com)"
        }
        
        for attempt in range(retries):
            t0 = time.time()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.get(url, params=params, headers=headers)
                    latency = (time.time() - t0) * 1000
                    
                    if res.status_code == 200:
                        metrics.record_provider_call("osrm", latency, True)
                        return res.json()
                    
                    if res.status_code == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                        
                    metrics.record_provider_call("osrm", latency, False)
                    return None
            except Exception as e:
                latency = (time.time() - t0) * 1000
                metrics.record_provider_call("osrm", latency, False)
                logger.warning(f"OSRM request failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
        return None

    async def get_route(self, mode: str, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> Dict[str, Any]:
        """mode can be 'driving', 'walking', 'cycling'"""
        profile = mode
        if mode == "transit": 
            profile = "walking" # Fallback heuristic
            
        coords = f"{start_lng},{start_lat};{end_lng},{end_lat}"
        
        cached = cache_get("osrm", "route", f"{profile}_{coords}")
        if cached:
            return cached
            
        data = await self._make_request(profile, coords)
        if data and data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            result = {
                "status": "success",
                "distance_meters": route.get("distance", 0),
                "duration_seconds": route.get("duration", 0),
                "geometry": route.get("geometry"),
                "source": "osrm",
                "mode": mode
            }
            cache_set("osrm", "route", f"{profile}_{coords}", result)
            return result
            
        return {
            "status": "error",
            "explanation": f"Could not route from {start_lat},{start_lng} to {end_lat},{end_lng} via {mode}"
        }

# Register OSRM Provider
registry.register(OSRMProvider())

class RoutingService:
    def __init__(self):
        self.provider = OSRMProvider()
        
    async def get_route(self, mode: str, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> Dict[str, Any]:
        return await self.provider.get_route(mode, start_lat, start_lng, end_lat, end_lng)
