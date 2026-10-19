"""
Places provider — POI discovery (restaurants, shops, services).

Delegates to Google Places, Yelp, and OSM.
"""

import logging
from typing import Dict, Any
from .base import BaseProvider, ProviderCapability

logger = logging.getLogger(__name__)


class PlacesProvider(BaseProvider):
    """
    Provides POI search and place details.
    - Search for places by category (restaurants, shops, etc.)
    - Get place details
    - Search by user preferences
    """

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            id="places",
            name="Places Provider",
            is_primary=True,
            requires_key=True,
            domains=["places", "restaurants", "shops", "services"],
        )

    def is_configured(self) -> bool:
        """Check if at least one place provider has API keys."""
        # In production: check GOOGLE_PLACES_API_KEY or YELP_API_KEY
        return True  # Placeholder

    async def search(
        self,
        query: str,
        lat: float,
        lng: float,
        radius: int = 1000,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Search for places near a location.

        Returns:
            {
                "results": [
                    {
                        "id": "place_123",
                        "name": "Restaurant Name",
                        "address": "...",
                        "lat": 42.123,
                        "lng": -71.456,
                        "rating": 4.5,
                        "category": "restaurant",
                        "source": "google_places|yelp|osm",
                    },
                    ...
                ],
                "source": "google_places|yelp|mixed|fallback",
                "error": null,
            }
        """
        try:
            if not query or not isinstance(query, str):
                return self._safe_dict(error="Invalid query")
            if lat is None or lng is None:
                return self._safe_dict(error="Invalid coordinates")

            # Placeholder: delegate to GooglePlacesService or YelpService
            return {
                "results": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"PlacesProvider.search failed: {e}")
            return self._safe_dict(error=str(e))

    async def search_by_category(
        self,
        category: str,
        lat: float,
        lng: float,
        radius: int = 1000,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Search for places by category (restaurant, cafe, shop, etc.).

        Returns same structure as search().
        """
        try:
            if not category or not isinstance(category, str):
                return self._safe_dict(error="Invalid category")
            if lat is None or lng is None:
                return self._safe_dict(error="Invalid coordinates")

            # Placeholder
            return {
                "results": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"PlacesProvider.search_by_category failed: {e}")
            return self._safe_dict(error=str(e))

    async def get_details(self, place_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a place.

        Returns:
            {
                "id": "place_123",
                "name": "...",
                "address": "...",
                "description": "...",
                "rating": 4.5,
                "photos": [...],
                "source": "google_places|yelp",
                "error": null,
            }
        """
        try:
            if not place_id or not isinstance(place_id, str):
                return self._safe_dict(error="Invalid place_id")

            # Placeholder
            return {
                "id": place_id,
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"PlacesProvider.get_details failed: {e}")
            return self._safe_dict(error=str(e))
