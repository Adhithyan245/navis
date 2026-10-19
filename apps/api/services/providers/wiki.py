import aiohttp
import urllib.parse
from apps.api.services.providers.base import BaseProvider
from apps.api.observability.circuit_breaker import circuit_breaker
from apps.api.services.cache.ttl_cache import ttl_cache

class WikiProvider(BaseProvider):
    @ttl_cache(ttl=86400)
    @circuit_breaker(threshold=3, timeout=30)
    async def fetch(self, topic: str) -> dict:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12, connect=5)) as session:
            safe_topic = urllib.parse.quote(topic)
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_topic}"
            headers = {"User-Agent": "NavisOrchestrator/1.0"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"title": data.get("title"), "extract": data.get("extract")}
        
        raise ValueError("Wiki API failed.")
