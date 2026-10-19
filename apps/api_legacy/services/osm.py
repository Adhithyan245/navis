import time
import httpx
import asyncio
from typing import Dict, Any, List
from services.cache import cache_get, cache_set
from services.metrics import metrics
from services.provider_base import BaseProvider, ProviderCapability, registry


class OSMProvider(BaseProvider):
    def __init__(self):
        self.overpass_url = "https://overpass-api.de/api/interpreter"
        self._capability = ProviderCapability(
            id="osm_overpass",
            name="OpenStreetMap Overpass API",
            is_primary=True,
            requires_key=False,
            domains=["services", "taste", "work", "settle"]
        )

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    # Expanded category coverage
    TAG_MAP = {
        "healthcare": "amenity=hospital",
        "hospital": "amenity=hospital",
        "pharmacy": "amenity=pharmacy",
        "emergency": "emergency=yes",
        "police": "amenity=police",
        "urgent_care": "amenity=clinic",
        "fire_station": "amenity=fire_station",
        "dentist": "amenity=dentist",
        "veterinary": "amenity=veterinary",
        "post_office": "amenity=post_office",
        "library": "amenity=library",
        "bank": "amenity=bank",
        "atm": "amenity=atm",
        "restaurant": "amenity=restaurant",
        "cafe": "amenity=cafe",
        "fast_food": "amenity=fast_food",
        "bar": "amenity=bar",
        "school": "amenity=school",
        "park": "leisure=park",
        "gym": "leisure=fitness_centre",
        "grocery store": "shop=supermarket",
        "supermarket": "shop=supermarket",
        "coworking": "amenity=coworking_space",
        "apartments": "building=apartments",
        "coffee": "amenity=cafe"
    }

    async def search_services(self, city: str, category: str, retries=2) -> Dict[str, Any]:
        tag = self.TAG_MAP.get(category)
        if tag is None:
            return {
                "status": "error",
                "services": [],
                "explanation": f"Unknown service category: '{category}'. Supported: {', '.join(sorted(self.TAG_MAP.keys()))}."
            }

        # Check cache
        cached = cache_get("osm_overpass", city, category)
        if cached is not None:
            return cached

        query = f"""
        [out:json][timeout:10];
        area[name="{city}"]->.searchArea;
        (
          node[{tag}](area.searchArea);
          way[{tag}](area.searchArea);
        );
        out center 20;
        """

        headers = {
            "User-Agent": "NavisOpenInfraBot/1.0 (navis@example.com)"
        }

        t0 = time.time()
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    res = await client.post(
                        self.overpass_url,
                        data={"data": query},
                        headers=headers
                    )
                    latency = (time.time() - t0) * 1000

                    if res.status_code == 200:
                        elements = res.json().get("elements", [])
                        normalized = []
                        for el in elements:
                            tags = el.get("tags", {})
                            name = tags.get("name")
                            if name is None:
                                continue
                            lat = el.get("lat") or (el.get("center", {}) or {}).get("lat")
                            lng = el.get("lon") or (el.get("center", {}) or {}).get("lon")
                            if lat is None or lng is None:
                                continue

                            normalized.append({
                                "id": str(el.get("id", "")),
                                "name": name,
                                "type": category,
                                "location": {"lat": lat, "lng": lng},
                                "address": tags.get("addr:street"),
                                "phone": tags.get("phone"),
                                "website": tags.get("website"),
                                "rating": tags.get("stars"), # Overpass sometimes has stars
                                "source_type": "live_api",
                                "source": "osm_overpass"
                            })

                        result = {
                            "status": "success" if normalized else "fallback",
                            "services": normalized,
                            "explanation": f"Found {len(normalized)} {category} locations via OSM." if normalized else f"No {category} locations found in OSM for {city}."
                        }
                        metrics.record_provider_call("osm_overpass", latency, bool(normalized))
                        if result["status"] == "success":
                            cache_set("osm_overpass", city, category, result)
                        return result
                    
                    if res.status_code == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue

                    metrics.record_provider_call("osm_overpass", latency, False)
                    return {"status": "error", "services": [], "explanation": f"OSM Overpass returned HTTP {res.status_code}."}
            except httpx.TimeoutException:
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                latency = (time.time() - t0) * 1000
                metrics.record_provider_call("osm_overpass", latency, False)
                return {"status": "error", "services": [], "explanation": "OSM Overpass API timed out."}
            except Exception as e:
                latency = (time.time() - t0) * 1000
                metrics.record_provider_call("osm_overpass", latency, False)
                return {"status": "error", "services": [], "explanation": f"OSM Overpass request failed: {str(e)}"}
        return {"status": "error", "services": [], "explanation": "Max retries exceeded"}

# Register OSM Provider
registry.register(OSMProvider())

class ServicesService:
    def __init__(self):
        self.provider = OSMProvider()

    def supported_categories(self):
        return sorted(OSMProvider.TAG_MAP.keys())

    async def get_services(self, city: str, category: str) -> Dict[str, Any]:
        return await self.provider.search_services(city, category)
