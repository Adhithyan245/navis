import aiohttp
from apps.api.services.providers.base import BaseProvider
from apps.api.observability.circuit_breaker import circuit_breaker
from apps.api.core.config import settings

class TransitProvider(BaseProvider):
    @circuit_breaker(threshold=3, timeout=30)
    async def fetch(self, start_coords: tuple, end_coords: tuple) -> dict:
        if not settings.OPENROUTESERVICE_API_KEY:
            raise ValueError("OpenRouteService API key missing")
            
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12, connect=5)) as session:
            url = "https://api.openrouteservice.org/v2/directions/driving-car"
            headers = {
                "Authorization": settings.OPENROUTESERVICE_API_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "coordinates": [list(start_coords), list(end_coords)]
            }
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                else:
                    err = await resp.text()
                    raise ValueError(f"Transit API failed: {err}")
