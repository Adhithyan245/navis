"""
Ticketmaster Discovery API service — optional enrichment for Connect agent.

Free tier available. Get credentials: https://developer.ticketmaster.com

Activated only when TICKETMASTER_API_KEY is set.
Normalizes to the same event schema as Eventbrite.
"""

import time
import httpx
from typing import Dict, Any
from core.config import settings
from services.cache import cache_get, cache_set
from services.metrics import metrics


class TicketmasterService:
    REQUIRED_API = "ticketmaster"

    BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

    async def search_events(
        self,
        city: str,
        query: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        from core.dependencies import assert_api_available
        assert_api_available(self.REQUIRED_API)

        cache_key = f"{query}|{category}"
        cached = cache_get("ticketmaster", city, cache_key)
        if cached is not None:
            return cached

        params = {
            "apikey": settings.ticketmaster_api_key,
            "city": city,
            "size": 10,
        }
        if query:
            params["keyword"] = query
        if category:
            params["classificationName"] = category

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(self.BASE_URL, params=params)
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    embedded = res.json().get("_embedded", {})
                    raw_events = embedded.get("events", [])
                    normalized = []
                    for e in raw_events:
                        name = e.get("name")
                        if not name:
                            continue

                        start = e.get("dates", {}).get("start", {})
                        start_time = start.get("dateTime", start.get("localDate", ""))

                        # Extract venue
                        venues = e.get("_embedded", {}).get("venues", [{}])
                        venue = venues[0] if venues else {}
                        venue_name = venue.get("name")
                        venue_loc = venue.get("location", {})
                        try:
                            lat = float(venue_loc.get("latitude", 0)) or None
                            lng = float(venue_loc.get("longitude", 0)) or None
                        except (TypeError, ValueError):
                            lat, lng = None, None

                        # Extract category
                        classifications = e.get("classifications", [{}])
                        segment = classifications[0].get("segment", {}).get("name") if classifications else None

                        normalized.append({
                            "id": e.get("id", ""),
                            "title": name,
                            "start_time": start_time,
                            "category": segment,
                            "location": {"name": venue_name, "lat": lat, "lng": lng},
                            "url": e.get("url", ""),
                            "source_type": "live_api",
                            "source": "ticketmaster",
                        })

                    result = {
                        "status": "success" if normalized else "fallback",
                        "events": normalized,
                        "explanation": (
                            f"Found {len(normalized)} events via Ticketmaster."
                            if normalized
                            else "Ticketmaster returned no events for this query."
                        ),
                    }
                    metrics.record_provider_call("ticketmaster", latency, bool(normalized))
                    if result["status"] == "success":
                        cache_set("ticketmaster", city, cache_key, result)
                    return result

                metrics.record_provider_call("ticketmaster", latency, False)
                return {
                    "status": "error",
                    "events": [],
                    "explanation": f"Ticketmaster API returned HTTP {res.status_code}.",
                }

        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("ticketmaster", latency, False)
            return {"status": "error", "events": [], "explanation": "Ticketmaster API timed out."}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("ticketmaster", latency, False)
            return {"status": "error", "events": [], "explanation": f"Ticketmaster request failed: {e}"}
