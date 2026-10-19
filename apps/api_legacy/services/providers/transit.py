"""
Transit provider — public transportation services.

Delegates to MBTA, GTFS, and other transit APIs.
"""

import logging
from typing import Dict, Any
from .base import BaseProvider, ProviderCapability

logger = logging.getLogger(__name__)


class TransitProvider(BaseProvider):
    """
    Provides public transportation information.
    - Search for routes
    - Get schedule information
    - Plan trips
    """

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            id="transit",
            name="Transit Provider",
            is_primary=True,
            requires_key=True,
            domains=["transit", "routes", "schedules"],
        )

    def is_configured(self) -> bool:
        """Check if transit provider has API keys."""
        # In production: check MBTA_API_KEY, GTFS data availability, etc.
        return True  # Placeholder

    async def search_routes(
        self,
        lat: float,
        lng: float,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for transit routes near a location.

        Returns:
            {
                "results": [
                    {
                        "id": "route_123",
                        "name": "Route 1",
                        "type": "bus|train|subway",
                        "operator": "MBTA",
                        "stops": [...],
                    },
                    ...
                ],
                "source": "mbta|gtfs|fallback",
                "error": null,
            }
        """
        try:
            if lat is None or lng is None:
                return self._safe_dict(error="Invalid coordinates")

            # Placeholder: delegate to TransitService, GTFSService
            return {
                "results": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"TransitProvider.search_routes failed: {e}")
            return self._safe_dict(error=str(e))

    async def get_schedule(
        self,
        route_id: str,
        date: str = "",  # YYYY-MM-DD
    ) -> Dict[str, Any]:
        """
        Get schedule for a transit route.

        Returns:
            {
                "route_id": "route_123",
                "date": "2026-05-12",
                "stops": [
                    {
                        "id": "stop_123",
                        "name": "Central Station",
                        "times": ["08:00", "08:15", "08:30", ...],
                    },
                    ...
                ],
                "source": "mbta|gtfs",
                "error": null,
            }
        """
        try:
            if not route_id or not isinstance(route_id, str):
                return self._safe_dict(error="Invalid route_id")

            # Placeholder
            return {
                "route_id": route_id,
                "stops": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"TransitProvider.get_schedule failed: {e}")
            return self._safe_dict(error=str(e))

    async def plan_trip(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> Dict[str, Any]:
        """
        Plan a transit trip between two locations.

        Returns:
            {
                "routes": [
                    {
                        "legs": [
                            {
                                "type": "walk|bus|train",
                                "distance": 100,
                                "duration": 300,
                                "instructions": "...",
                            },
                            ...
                        ],
                        "distance": 5000,
                        "duration": 1200,
                        "emissions": 50,
                    },
                    ...
                ],
                "source": "transit_planner|fallback",
                "error": null,
            }
        """
        try:
            if None in [origin_lat, origin_lng, dest_lat, dest_lng]:
                return self._safe_dict(error="Invalid coordinates")

            # Placeholder
            return {
                "routes": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"TransitProvider.plan_trip failed: {e}")
            return self._safe_dict(error=str(e))
