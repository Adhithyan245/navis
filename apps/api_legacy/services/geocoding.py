import time
import httpx
import asyncio
from typing import Dict, Any, Optional
from services.cache import cache_get, cache_set
from services.metrics import metrics
from services.provider_base import BaseProvider, ProviderCapability, registry
import logging

logger = logging.getLogger(__name__)

class NominatimProvider(BaseProvider):
    def __init__(self):
        self.url = "https://nominatim.openstreetmap.org/search"
        self.reverse_url = "https://nominatim.openstreetmap.org/reverse"
        self._capability = ProviderCapability(
            id="nominatim_geocoding",
            name="Nominatim Geocoding API",
            is_primary=True,
            requires_key=False,
            domains=["geocoding"]
        )

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    async def _make_request(self, url: str, params: dict, retries: int = 2) -> Optional[dict]:
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
                        metrics.record_provider_call("nominatim", latency, True)
                        return res.json()
                    
                    if res.status_code == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                        
                    metrics.record_provider_call("nominatim", latency, False)
                    return None
            except Exception as e:
                latency = (time.time() - t0) * 1000
                metrics.record_provider_call("nominatim", latency, False)
                logger.warning(f"Nominatim request failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
        return None

    async def geocode(self, query: str, city: str = "") -> Dict[str, Any]:
        full_query = f"{query}, {city}" if city else query
        
        cached = cache_get("nominatim", "geocode", full_query)
        if cached:
            return cached
            
        params = {
            "q": full_query,
            "format": "json",
            "limit": 1
        }
        
        data = await self._make_request(self.url, params)
        if data and len(data) > 0:
            result = {
                "status": "success",
                "location": {
                    "lat": float(data[0]["lat"]),
                    "lng": float(data[0]["lon"])
                },
                "display_name": data[0].get("display_name", "")
            }
            cache_set("nominatim", "geocode", full_query, result)
            return result
            
        return {
            "status": "error",
            "explanation": f"Could not geocode '{full_query}'"
        }

    async def reverse_geocode(self, lat: float, lng: float) -> Dict[str, Any]:
        cached = cache_get("nominatim", "reverse", f"{lat},{lng}")
        if cached:
            return cached
            
        params = {
            "lat": lat,
            "lon": lng,
            "format": "json"
        }
        
        data = await self._make_request(self.reverse_url, params)
        if data and "address" in data:
            addr = data["address"]
            result = {
                "status": "success",
                "neighborhood": addr.get("neighbourhood") or addr.get("suburb") or addr.get("city_district") or "",
                "city": addr.get("city") or addr.get("town") or addr.get("village") or "",
                "display_name": data.get("display_name", "")
            }
            cache_set("nominatim", "reverse", f"{lat},{lng}", result)
            return result
            
        return {
            "status": "error",
            "explanation": f"Could not reverse geocode {lat},{lng}"
        }

# Register Nominatim Provider
registry.register(NominatimProvider())

class GeocodingService:
    def __init__(self):
        self.provider = NominatimProvider()
        
    async def geocode(self, query: str, city: str = "") -> Dict[str, Any]:
        return await self.provider.geocode(query, city)
        
    async def reverse_geocode(self, lat: float, lng: float) -> Dict[str, Any]:
        return await self.provider.reverse_geocode(lat, lng)
