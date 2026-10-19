import aiohttp
from apps.api.services.providers.base import BaseProvider
from apps.api.observability.circuit_breaker import circuit_breaker
from apps.api.core.config import settings

class EventsProvider(BaseProvider):
    @circuit_breaker(threshold=3, timeout=30)
    async def fetch(self, lat: float, lon: float, radius: int = 10) -> list:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12, connect=5)) as session:
            # Ticketmaster Primary
            if settings.TICKETMASTER_API_KEY:
                url = f"https://app.ticketmaster.com/discovery/v2/events.json?latlong={lat},{lon}&radius={radius}&apikey={settings.TICKETMASTER_API_KEY}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "_embedded" in data and "events" in data["_embedded"]:
                            return data["_embedded"]["events"]
            
            # No Eventbrite fallback: its public location search
            # (/v3/events/search) was retired, and the remaining API only
            # lists events for an organization or venue you already know.

        raise ValueError("Events APIs failed or keys are missing.")
