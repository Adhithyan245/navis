import os
from core.dependencies import assert_api_available
import time
import httpx
from typing import Dict, Any
from services.cache import cache_get, cache_set
from services.metrics import metrics


class EventbriteProvider:
    REQUIRED_API = "eventbrite"

    def __init__(self):
        self.api_key = os.getenv("EVENTBRITE_API_KEY")
        self.base_url = "https://www.eventbriteapi.com/v3"

    async def search_events(
        self, city: str, query: str = "",
        category: str = "", time_filter: str = ""
    ) -> Dict[str, Any]:
        from core.dependencies import assert_api_available
        assert_api_available(self.REQUIRED_API)

        # Removed redundant api_key check since assert handles it

        # Build cache key from all filter dimensions
        cache_query = f"{query}|{category}|{time_filter}"
        cached = cache_get("eventbrite", city, cache_query)
        if cached is not None:
            return cached

        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"location.address": city}
        if query:
            params["q"] = query
        if category:
            params["categories"] = category
        if time_filter == "today":
            params["start_date.keyword"] = "today"
        elif time_filter == "this_week":
            params["start_date.keyword"] = "this_week"
        elif time_filter == "this_month":
            params["start_date.keyword"] = "this_month"

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(
                    f"{self.base_url}/events/search/",
                    headers=headers, params=params,
                )
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    raw_events = res.json().get("events", [])
                    normalized = []
                    for e in raw_events:
                        # Validate name structure
                        name_obj = e.get("name")
                        if not isinstance(name_obj, dict):
                            continue
                        title = name_obj.get("text")
                        if not title:
                            continue

                        # Extract start time
                        start_obj = e.get("start", {})
                        start_time = start_obj.get("utc", "") if isinstance(start_obj, dict) else ""

                        # Extract venue if available
                        venue_obj = e.get("venue")
                        venue_name = None
                        venue_lat = None
                        venue_lng = None
                        if isinstance(venue_obj, dict):
                            venue_name = venue_obj.get("name")
                            addr = venue_obj.get("address", {})
                            if isinstance(addr, dict):
                                venue_lat = addr.get("latitude")
                                venue_lng = addr.get("longitude")
                                # Convert string coords to float
                                if isinstance(venue_lat, str):
                                    try:
                                        venue_lat = float(venue_lat)
                                    except (ValueError, TypeError):
                                        venue_lat = None
                                if isinstance(venue_lng, str):
                                    try:
                                        venue_lng = float(venue_lng)
                                    except (ValueError, TypeError):
                                        venue_lng = None

                        # Extract category
                        cat_obj = e.get("category", {})
                        event_category = cat_obj.get("short_name") if isinstance(cat_obj, dict) else None

                        normalized.append({
                            "id": str(e.get("id", "")),
                            "title": title,
                            "start_time": start_time,
                            "category": event_category,
                            "location": {
                                "name": venue_name,
                                "lat": venue_lat,
                                "lng": venue_lng,
                            },
                            "source_type": "live_api",
                            "source": "eventbrite"
                        })

                    result = {
                        "status": "success" if normalized else "fallback",
                        "events": normalized,
                        "explanation": f"Fetched {len(normalized)} events from Eventbrite." if normalized else "Eventbrite returned no events for this query."
                    }
                    metrics.record_provider_call("eventbrite", latency, bool(normalized))
                    if result["status"] == "success":
                        cache_set("eventbrite", city, cache_query, result)
                    return result
                else:
                    metrics.record_provider_call("eventbrite", latency, False)
                    return {
                        "status": "error",
                        "events": [],
                        "explanation": f"Eventbrite returned HTTP {res.status_code}."
                    }
        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("eventbrite", latency, False)
            return {"status": "error", "events": [], "explanation": "Eventbrite API timed out."}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("eventbrite", latency, False)
            return {"status": "error", "events": [], "explanation": f"Eventbrite request failed: {str(e)}"}


class ConnectService:
    REQUIRED_API = "eventbrite"

    def __init__(self):
        self.provider = EventbriteProvider()

    async def get_events(
        self, city: str, query: str = "",
        category: str = "", time_filter: str = ""
    ) -> Dict[str, Any]:
        return await self.provider.search_events(city, query, category, time_filter)
