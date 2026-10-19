"""
Zillow API wrapper (via RapidAPI).
Required API for Settle Agent.
"""

import time
import httpx
from core.dependencies import assert_api_available
from core.config import settings
from services.metrics import metrics
from services.cache import cache_get, cache_set

class ZillowService:
    REQUIRED_API = "zillow"
    BASE_URL = "https://zillow-com1.p.rapidapi.com/propertyExtendedSearch"

    async def search_housing(self, query: str, city: str) -> dict:
        assert_api_available(self.REQUIRED_API)
        
        cache_key = f"{city}|{query}"
        cached = cache_get("zillow", city, cache_key)
        if cached is not None:
            return cached

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    self.BASE_URL,
                    headers={
                        "X-RapidAPI-Key": settings.zillow_api_key,
                        "X-RapidAPI-Host": "zillow-com1.p.rapidapi.com"
                    },
                    params={"location": city}
                )
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    data = res.json()
                    props = data.get("props", [])
                    listings = []
                    for p in props[:10]:
                        listings.append({
                            "id": p.get("zpid"),
                            "title": f"{p.get('bedrooms', 0)}bd {p.get('bathrooms', 0)}ba",
                            "address": p.get("address", ""),
                            "price": p.get("price", 0),
                            "property_type": p.get("propertyType", ""),
                            "url": f"https://www.zillow.com/homedetails/{p.get('zpid')}_zpid/" if p.get("zpid") else "",
                            "source": "zillow"
                        })
                    
                    result = {
                        "status": "success",
                        "listings": listings,
                        "explanation": f"Found {len(listings)} listings in {city} via Zillow."
                    }
                    metrics.record_provider_call("zillow", latency, bool(listings))
                    if result["status"] == "success":
                        cache_set("zillow", city, cache_key, result)
                    return result
                
                metrics.record_provider_call("zillow", latency, False)
                return {
                    "status": "error",
                    "listings": [],
                    "message": f"Zillow API returned HTTP {res.status_code}.",
                    "_reason": "api_error"
                }

        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("zillow", latency, False)
            return {"status": "error", "listings": [], "message": "Zillow API timed out.", "_reason": "timeout"}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("zillow", latency, False)
            return {"status": "error", "listings": [], "message": f"Zillow request failed: {str(e)}", "_reason": "exception"}
