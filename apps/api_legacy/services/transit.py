"""
Transit provider abstraction.

Production-ready interface for multiple transit providers.
Each provider must implement get_routes() and get_alerts().

Current providers:
  - MBTAProvider (Boston) — static reference data
  - NYCMTAProvider (New York) — stub, documented integration points

Adding a new provider:
  1. Subclass TransitProvider
  2. Implement get_routes(city) and get_alerts(city)
  3. Register in TransitService._providers
  4. Add city entry in CityCapabilityRegistry with transit=True
"""

import os
import time
import httpx
from typing import Dict, Any
from services.cache import cache_get, cache_set
from services.metrics import metrics


class TransitProvider:
    """Abstract base for all transit providers."""
    provider_id: str = "unknown"

    async def get_routes(self, city: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def get_alerts(self, city: str) -> Dict[str, Any]:
        return {"alerts": []}


class MBTAProvider(TransitProvider):
    """MBTA provider for Boston metro area."""
    provider_id = "mbta"

    def __init__(self):
        self.api_key = os.getenv("MBTA_API_KEY")
        self.base_url = "https://api-v3.mbta.com"

    async def get_routes(self, city: str) -> Dict[str, Any]:
        if "boston" not in city.lower():
            return {"status": "error", "explanation": "MBTA only supports Boston metro area."}

        # Check cache
        cached = cache_get("mbta", city, "routes")
        if cached is not None:
            return cached

        # Try live API if key exists
        if self.api_key:
            t0 = time.time()
            try:
                headers = {"x-api-key": self.api_key}
                async with httpx.AsyncClient(timeout=8.0) as client:
                    res = await client.get(f"{self.base_url}/routes", headers=headers, params={"filter[type]": "0,1"})
                    latency = (time.time() - t0) * 1000

                    if res.status_code == 200:
                        raw = res.json().get("data", [])
                        routes = []
                        for r in raw:
                            attrs = r.get("attributes", {})
                            routes.append({
                                "id": r.get("id"),
                                "name": attrs.get("long_name", attrs.get("short_name", "")),
                                "mode": attrs.get("description", "rail"),
                                "color": attrs.get("color"),
                                "source": "mbta",
                            })
                        result = {"status": "success", "routes": routes, "stops": [], "alerts": []}
                        metrics.record_provider_call("mbta", latency, True)
                        cache_set("mbta", city, "routes", result)
                        return result
                    else:
                        metrics.record_provider_call("mbta", latency, False)
            except httpx.TimeoutException:
                latency = (time.time() - t0) * 1000
                metrics.record_provider_call("mbta", latency, False)
            except Exception:
                latency = (time.time() - t0) * 1000
                metrics.record_provider_call("mbta", latency, False)

        from core.dependencies import assert_api_available
        assert_api_available("mbta")
        
        # If API failed or timed out above, it returns error now
        return {"status": "error", "explanation": "MBTA API failed or timed out", "_reason": "api_timeout"}

    async def get_alerts(self, city: str) -> Dict[str, Any]:
        if not self.api_key:
            return {"alerts": []}
        t0 = time.time()
        try:
            headers = {"x-api-key": self.api_key}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/alerts", headers=headers, params={"filter[activity]": "BOARD,RIDE"})
                latency = (time.time() - t0) * 1000
                if res.status_code == 200:
                    raw = res.json().get("data", [])
                    alerts = []
                    for a in raw[:10]:
                        attrs = a.get("attributes", {})
                        alerts.append({
                            "id": a.get("id"),
                            "header": attrs.get("header", ""),
                            "severity": attrs.get("severity"),
                            "source": "mbta",
                        })
                    metrics.record_provider_call("mbta", latency, True)
                    return {"alerts": alerts}
                metrics.record_provider_call("mbta", latency, False)
        except Exception:
            pass
        return {"alerts": []}


class TransitService:
    """Registry of city-to-provider mappings. Add new providers here."""

    def __init__(self):
        self._providers: Dict[str, TransitProvider] = {
            "boston": MBTAProvider(),
        }

    def get_provider(self, city: str) -> TransitProvider | None:
        return self._providers.get(city.lower().strip())

    async def get_transit_info(self, city: str) -> Dict[str, Any]:
        provider = self.get_provider(city)
        if provider is None:
            return {"status": "error", "explanation": f"No transit provider registered for {city}."}
        routes_res = await provider.get_routes(city)
        if routes_res.get("status") != "success":
            return routes_res
        # Merge alerts
        alerts_res = await provider.get_alerts(city)
        routes_res["alerts"] = alerts_res.get("alerts", [])
        return routes_res
