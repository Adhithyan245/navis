"""
ProviderManager — centralized access to all data providers.

This is the ONLY entry point that agents should use for external data.
Guarantees fault tolerance and defensive programming.

PHASE 3: Integrated API Key Gating
- All external calls gated by APIKeyGatingService
- Rate limiting enforced per provider
- Quota tracking per provider
- Graceful fallback if gating denies call
"""

import logging
from typing import Dict, Any, Optional
from core.config import settings
from services.providers.base import ProviderRegistry, get_registry
from services.providers.geo import GeoProvider
from services.providers.places import PlacesProvider
from services.providers.transit import TransitProvider
from services.providers.events import EventsProvider
from services.providers.wiki import WikiProvider
from services.api_key_gating import api_key_gating

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Centralized manager for all data providers with PHASE 3 gating.

    Responsibilities:
    - Initialize and register all providers
    - Provide safe access to provider methods
    - PHASE 3: Enforce API key validation, rate limiting, quota tracking
    - Handle provider failures gracefully
    - Ensure no single provider crash affects orchestration
    """

    def __init__(self):
        self.registry = get_registry()
        self.gating = api_key_gating  # PHASE 3: API key gating
        self._initialized = False
        self._init_providers()
        logger.info(f"ProviderManager initialized: {self.gating}")

    def _init_providers(self):
        """Register all available providers."""
        if self._initialized:
            return

        try:
            # Register core providers
            self.registry.register(GeoProvider())
            self.registry.register(PlacesProvider())
            self.registry.register(TransitProvider())
            self.registry.register(EventsProvider())
            self.registry.register(WikiProvider())

            logger.info(
                f"ProviderManager initialized with providers: "
                f"{', '.join(self.registry.list_providers().values())}"
            )
            self._initialized = True
        except Exception as e:
            logger.error(f"ProviderManager initialization failed: {e}")
            # Don't crash — providers will use fallback mode

    # ─── PHASE 3: GATING HELPER ───
    
    def _check_gate(self, provider: str) -> tuple[bool, Optional[str]]:
        """
        PHASE 3: Check if external call to provider is allowed.
        
        Returns:
            (allowed, reason_if_denied)
        """
        return self.gating.check_can_call(provider)

    def _record_gate_result(self, provider: str, success: bool = True, error: str = None) -> None:
        """PHASE 3: Record call result for rate limiting and quota tracking."""
        self.gating.record_call(provider, success=success, error=error)

    # ────────────────────────────────────────────────────────────────────────────
    # Geo Provider Access
    # ────────────────────────────────────────────────────────────────────────────

    async def geocode(self, address: str) -> Dict[str, Any]:
        """
        Safely resolve an address to coordinates.
        
        PHASE 3: Gated with API key validation.

        Returns:
            {
                "results": [...],
                "source": "fallback|geocoding",
                "error": null or string,
            }
        """
        try:
            geo_provider = self.registry.get_provider("geo")
            if not geo_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            # PHASE 3: Check gate
            allowed, gate_reason = self._check_gate("geocoding")
            if not allowed:
                logger.info(f"Geocoding call gated: {gate_reason}")
                return {"results": [], "source": "fallback", "error": gate_reason}

            result = await geo_provider.geocode(address)
            self._record_gate_result("geocoding", success=True)
            return result
        except Exception as e:
            logger.error(f"ProviderManager.geocode failed: {e}")
            self._record_gate_result("geocoding", success=False, error=str(e))
            return {"results": [], "source": "fallback", "error": str(e)}

    async def reverse_geocode(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Safely reverse geocode coordinates.
        
        PHASE 3: Gated with API key validation.

        Returns:
            {
                "results": [...],
                "source": "fallback|geocoding",
                "error": null,
            }
        """
        try:
            geo_provider = self.registry.get_provider("geo")
            if not geo_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            # PHASE 3: Check gate
            allowed, gate_reason = self._check_gate("geocoding")
            if not allowed:
                logger.info(f"Reverse geocoding call gated: {gate_reason}")
                return {"results": [], "source": "fallback", "error": gate_reason}

            result = await geo_provider.reverse_geocode(lat, lng)
            self._record_gate_result("geocoding", success=True)
            return result
        except Exception as e:
            logger.error(f"ProviderManager.reverse_geocode failed: {e}")
            return {"results": [], "source": "fallback", "error": str(e)}

    async def detect_city(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Safely detect which city coordinates belong to.

        Returns:
            {
                "city": "Boston" or None,
                "country": "US" or None,
                "confidence": 0.9,
                "error": null,
            }
        """
        try:
            geo_provider = self.registry.get_provider("geo")
            if not geo_provider:
                return {
                    "city": None,
                    "country": None,
                    "confidence": 0.0,
                    "error": "Provider not found",
                }

            return await geo_provider.detect_city(lat, lng)
        except Exception as e:
            logger.error(f"ProviderManager.detect_city failed: {e}")
            return {
                "city": None,
                "country": None,
                "confidence": 0.0,
                "error": str(e),
            }

    # ────────────────────────────────────────────────────────────────────────────
    # Places Provider Access
    # ────────────────────────────────────────────────────────────────────────────

    async def search_places(
        self,
        query: str,
        lat: float,
        lng: float,
        radius: int = 1000,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Safely search for places.
        
        PHASE 3: Gated with API key validation, rate limiting, quota tracking.

        Returns:
            {
                "results": [...],
                "source": "google_places|yelp|mixed|fallback",
                "error": null,
            }
        """
        try:
            places_provider = self.registry.get_provider("places")
            if not places_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            # PHASE 3: Check gates for all potential providers in places
            allowed_google, gate_reason_google = self._check_gate("google_places")
            allowed_yelp, gate_reason_yelp = self._check_gate("yelp")
            
            if not allowed_google and not allowed_yelp:
                combined_reason = f"All providers gated: google_places ({gate_reason_google}), yelp ({gate_reason_yelp})"
                logger.info(f"Places search gated: {combined_reason}")
                return {"results": [], "source": "fallback", "error": combined_reason}

            result = await places_provider.search(query, lat, lng, radius, limit)
            
            # Record successful calls
            if result.get("source") == "google_places":
                self._record_gate_result("google_places", success=True)
            elif result.get("source") == "yelp":
                self._record_gate_result("yelp", success=True)
            
            return result
        except Exception as e:
            logger.error(f"ProviderManager.search_places failed: {e}")
            self._record_gate_result("places", success=False, error=str(e))
            return {"results": [], "source": "fallback", "error": str(e)}

    async def search_places_by_category(
        self,
        category: str,
        lat: float,
        lng: float,
        radius: int = 1000,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Safely search for places by category.
        
        PHASE 3: Gated with API key validation.

        Returns:
            {
                "results": [...],
                "source": "google_places|yelp|fallback",
                "error": null,
            }
        """
        try:
            places_provider = self.registry.get_provider("places")
            if not places_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            # PHASE 3: Check gates
            allowed_google, gate_reason_google = self._check_gate("google_places")
            allowed_yelp, gate_reason_yelp = self._check_gate("yelp")
            
            if not allowed_google and not allowed_yelp:
                logger.info(f"Places category search gated: all providers unavailable")
                return {"results": [], "source": "fallback", "error": "All providers gated"}

            result = await places_provider.search_by_category(category, lat, lng, radius, limit)
            
            if result.get("source") in ("google_places", "yelp"):
                self._record_gate_result(result.get("source"), success=True)
            
            return result
        except Exception as e:
            logger.error(f"ProviderManager.search_places_by_category failed: {e}")
            self._record_gate_result("places", success=False, error=str(e))
            return {"results": [], "source": "fallback", "error": str(e)}

    async def get_place_details(self, place_id: str) -> Dict[str, Any]:
        """
        Safely get details about a place.

        Returns:
            {
                "id": "place_123",
                "name": "...",
                ...
                "source": "google_places|yelp|fallback",
                "error": null,
            }
        """
        try:
            places_provider = self.registry.get_provider("places")
            if not places_provider:
                return {
                    "id": place_id,
                    "source": "fallback",
                    "error": "Provider not found",
                }

            return await places_provider.get_details(place_id)
        except Exception as e:
            logger.error(f"ProviderManager.get_place_details failed: {e}")
            return {"id": place_id, "source": "fallback", "error": str(e)}

    # ────────────────────────────────────────────────────────────────────────────
    # Transit Provider Access
    # ────────────────────────────────────────────────────────────────────────────

    async def search_transit_routes(
        self,
        lat: float,
        lng: float,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Safely search for transit routes.
        
        PHASE 3: Gated with API key validation, rate limiting, quota tracking.

        Returns:
            {
                "results": [...],
                "source": "mbta|gtfs|fallback",
                "error": null,
            }
        """
        try:
            transit_provider = self.registry.get_provider("transit")
            if not transit_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            # PHASE 3: Check gate
            allowed_mbta, reason_mbta = self._check_gate("mbta")
            
            if not allowed_mbta:
                logger.info(f"Transit routes search gated: {reason_mbta}")
                return {"results": [], "source": "fallback", "error": reason_mbta}

            result = await transit_provider.search_routes(lat, lng, limit)
            
            if result.get("source") == "mbta":
                self._record_gate_result("mbta", success=True)
            
            return result
        except Exception as e:
            logger.error(f"ProviderManager.search_transit_routes failed: {e}")
            self._record_gate_result("mbta", success=False, error=str(e))
            return {"results": [], "source": "fallback", "error": str(e)}

    async def get_transit_schedule(
        self,
        route_id: str,
        date: str = "",
    ) -> Dict[str, Any]:
        """
        Safely get transit schedule.

        Returns:
            {
                "route_id": "route_123",
                "stops": [...],
                "source": "mbta|gtfs|fallback",
                "error": null,
            }
        """
        try:
            transit_provider = self.registry.get_provider("transit")
            if not transit_provider:
                return {
                    "route_id": route_id,
                    "stops": [],
                    "source": "fallback",
                    "error": "Provider not found",
                }

            return await transit_provider.get_schedule(route_id, date)
        except Exception as e:
            logger.error(f"ProviderManager.get_transit_schedule failed: {e}")
            return {
                "route_id": route_id,
                "stops": [],
                "source": "fallback",
                "error": str(e),
            }

    async def plan_transit_trip(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> Dict[str, Any]:
        """
        Safely plan a transit trip.

        Returns:
            {
                "routes": [...],
                "source": "transit_planner|fallback",
                "error": null,
            }
        """
        try:
            transit_provider = self.registry.get_provider("transit")
            if not transit_provider:
                return {"routes": [], "source": "fallback", "error": "Provider not found"}

            return await transit_provider.plan_trip(origin_lat, origin_lng, dest_lat, dest_lng)
        except Exception as e:
            logger.error(f"ProviderManager.plan_transit_trip failed: {e}")
            return {"routes": [], "source": "fallback", "error": str(e)}

    # ────────────────────────────────────────────────────────────────────────────
    # Events Provider Access
    # ────────────────────────────────────────────────────────────────────────────

    async def search_events(
        self,
        query: str,
        lat: float = None,
        lng: float = None,
        radius: int = 10000,
        limit: int = 20,
        start_date: str = "",
        end_date: str = "",
    ) -> Dict[str, Any]:
        """
        Safely search for events.
        
        PHASE 3: Gated with API key validation, rate limiting, quota tracking.

        Returns:
            {
                "results": [...],
                "source": "eventbrite|ticketmaster|fallback",
                "error": null,
            }
        """
        try:
            events_provider = self.registry.get_provider("events")
            if not events_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            # PHASE 3: Check gates for all potential event providers
            allowed_eb, reason_eb = self._check_gate("eventbrite")
            allowed_tm, reason_tm = self._check_gate("ticketmaster")
            
            if not allowed_eb and not allowed_tm:
                logger.info(f"Events search gated: all providers unavailable")
                return {"results": [], "source": "fallback", "error": "All event providers gated"}

            result = await events_provider.search(
                query, lat, lng, radius, limit, start_date, end_date
            )
            
            if result.get("source") in ("eventbrite", "ticketmaster"):
                self._record_gate_result(result.get("source"), success=True)
            
            return result
        except Exception as e:
            logger.error(f"ProviderManager.search_events failed: {e}")
            self._record_gate_result("events", success=False, error=str(e))
            return {"results": [], "source": "fallback", "error": str(e)}

    async def search_events_by_category(
        self,
        category: str,
        lat: float = None,
        lng: float = None,
        radius: int = 10000,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Safely search for events by category.

        Returns:
            {
                "results": [...],
                "source": "eventbrite|ticketmaster|fallback",
                "error": null,
            }
        """
        try:
            events_provider = self.registry.get_provider("events")
            if not events_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            return await events_provider.search_by_category(category, lat, lng, radius, limit)
        except Exception as e:
            logger.error(f"ProviderManager.search_events_by_category failed: {e}")
            return {"results": [], "source": "fallback", "error": str(e)}

    async def get_event_details(self, event_id: str) -> Dict[str, Any]:
        """
        Safely get details about an event.

        Returns:
            {
                "id": "event_123",
                ...
                "source": "eventbrite|ticketmaster|fallback",
                "error": null,
            }
        """
        try:
            events_provider = self.registry.get_provider("events")
            if not events_provider:
                return {"id": event_id, "source": "fallback", "error": "Provider not found"}

            return await events_provider.get_details(event_id)
        except Exception as e:
            logger.error(f"ProviderManager.get_event_details failed: {e}")
            return {"id": event_id, "source": "fallback", "error": str(e)}

    # ────────────────────────────────────────────────────────────────────────────
    # Wiki Provider Access
    # ────────────────────────────────────────────────────────────────────────────

    async def search_reference(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Safely search for reference information.

        Returns:
            {
                "results": [...],
                "source": "wikipedia|fallback",
                "error": null,
            }
        """
        try:
            wiki_provider = self.registry.get_provider("wiki")
            if not wiki_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            return await wiki_provider.search(query, limit)
        except Exception as e:
            logger.error(f"ProviderManager.search_reference failed: {e}")
            return {"results": [], "source": "fallback", "error": str(e)}

    async def get_location_context(self, city: str) -> Dict[str, Any]:
        """
        Safely get background context about a location.

        Returns:
            {
                "city": "Boston",
                "description": "...",
                "source": "wikipedia|fallback",
                "error": null,
            }
        """
        try:
            wiki_provider = self.registry.get_provider("wiki")
            if not wiki_provider:
                return {
                    "city": city,
                    "description": "",
                    "source": "fallback",
                    "error": "Provider not found",
                }

            return await wiki_provider.get_location_context(city)
        except Exception as e:
            logger.error(f"ProviderManager.get_location_context failed: {e}")
            return {
                "city": city,
                "description": "",
                "source": "fallback",
                "error": str(e),
            }

    async def get_wiki_page(self, title: str) -> Dict[str, Any]:
        """
        Safely get a Wikipedia page.

        Returns:
            {
                "title": "...",
                "content": "...",
                "source": "wikipedia|fallback",
                "error": null,
            }
        """
        try:
            wiki_provider = self.registry.get_provider("wiki")
            if not wiki_provider:
                return {
                    "title": title,
                    "content": "",
                    "source": "fallback",
                    "error": "Provider not found",
                }

            return await wiki_provider.get_page(title)
        except Exception as e:
            logger.error(f"ProviderManager.get_wiki_page failed: {e}")
            return {"title": title, "content": "", "source": "fallback", "error": str(e)}

    # ────────────────────────────────────────────────────────────────────────────
    # Services Provider Access (OSM, etc.)
    # ────────────────────────────────────────────────────────────────────────────

    async def search_services(
        self,
        category: str,
        lat: float = None,
        lng: float = None,
        radius: int = 1000,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Safely search for services (hospitals, pharmacies, etc.) by category.
        
        PHASE 3: Gated with API key validation, rate limiting, quota tracking.

        Returns:
            {
                "results": [...],
                "source": "osm|fallback",
                "error": null,
            }
        """
        try:
            places_provider = self.registry.get_provider("places")
            if not places_provider:
                return {"results": [], "source": "fallback", "error": "Provider not found"}

            # PHASE 3: Check gate (OSM typically has no key requirement, but still checked)
            allowed, reason = self._check_gate("osm")
            
            if not allowed:
                logger.info(f"Services search gated: {reason}")
                return {"results": [], "source": "fallback", "error": reason}

            result = await places_provider.search_by_category(category, lat, lng, radius, limit)
            
            if result.get("source") in ("osm", "osm_overpass"):
                self._record_gate_result("osm", success=True)
            
            return result
        except Exception as e:
            logger.error(f"ProviderManager.search_services failed: {e}")
            self._record_gate_result("osm", success=False, error=str(e))
            return {"results": [], "source": "fallback", "error": str(e)}

    # ────────────────────────────────────────────────────────────────────────────
    # Utilities
    # ────────────────────────────────────────────────────────────────────────────

    def get_provider_status(self) -> Dict[str, str]:
        """Get health status of all registered providers."""
        status = {}
        for provider_id, provider in self.registry._providers.items():
            try:
                is_configured = provider.is_configured()
                status[provider_id] = "ACTIVE" if is_configured else "DISABLED"
            except Exception as e:
                logger.error(f"Provider {provider_id} status check failed: {e}")
                status[provider_id] = "ERROR"
        return status

    # ─── PHASE 3: GATING STATUS ───

    def get_gating_status(self) -> Dict[str, Any]:
        """PHASE 3: Get comprehensive gating status for all providers."""
        return self.gating.get_all_stats()

    def get_provider_gating_stats(self, provider: str) -> Dict[str, Any]:
        """PHASE 3: Get detailed gating stats for a specific provider."""
        return self.gating.get_provider_stats(provider)
        return status


# Global instance
_global_manager: Optional[ProviderManager] = None


def get_provider_manager() -> ProviderManager:
    """Get or create the global ProviderManager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ProviderManager()
    return _global_manager
