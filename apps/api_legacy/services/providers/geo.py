"""
Geo provider — geocoding and reverse geocoding.

Handles location resolution, coordinate parsing, and city detection.
"""

import logging
from typing import Dict, Any, Optional
from .base import BaseProvider, ProviderCapability

logger = logging.getLogger(__name__)


class GeoProvider(BaseProvider):
    """
    Provides geocoding services.
    - Resolve addresses to coordinates
    - Reverse geocode coordinates to addresses
    - Detect city from coordinates
    """

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            id="geo",
            name="Geocoding Provider",
            is_primary=True,
            requires_key=False,
            domains=["geocoding", "city_detection"],
        )

    def is_configured(self) -> bool:
        """Geo provider doesn't require keys — always configured."""
        return True

    async def geocode(self, address: str) -> Dict[str, Any]:
        """
        Resolve an address to coordinates and structured location data.

        Returns:
            {
                "results": [
                    {
                        "address": "...",
                        "lat": 42.123,
                        "lng": -71.456,
                        "city": "Boston",
                        "country": "US",
                        "confidence": 0.95,
                    }
                ],
                "source": "fallback|geocoding",
                "error": null or string,
            }
        """
        try:
            if not address or not isinstance(address, str):
                return self._safe_dict(error="Invalid address")

            # Placeholder: In production, delegate to GeocodingService
            # For now, return empty but valid result
            return {
                "results": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"GeoProvider.geocode failed: {e}")
            return self._safe_dict(error=str(e))

    async def reverse_geocode(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Reverse geocode coordinates to address.

        Returns:
            {
                "results": [
                    {
                        "address": "...",
                        "lat": 42.123,
                        "lng": -71.456,
                        "city": "Boston",
                        "country": "US",
                    }
                ],
                "source": "fallback|geocoding",
                "error": null,
            }
        """
        try:
            if lat is None or lng is None:
                return self._safe_dict(error="Invalid coordinates")

            # Placeholder
            return {
                "results": [],
                "source": "fallback",
                "error": None,
            }
        except Exception as e:
            logger.error(f"GeoProvider.reverse_geocode failed: {e}")
            return self._safe_dict(error=str(e))

    async def detect_city(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Detect which city the coordinates belong to.

        Returns:
            {
                "city": "Boston" or None,
                "country": "US" or None,
                "confidence": 0.9,
                "source": "fallback|detection",
                "error": null,
            }
        """
        try:
            if lat is None or lng is None:
                return {"city": None, "country": None, "confidence": 0.0, "error": "Invalid coordinates"}

            # Placeholder
            return {
                "city": None,
                "country": None,
                "confidence": 0.0,
                "error": None,
            }
        except Exception as e:
            logger.error(f"GeoProvider.detect_city failed: {e}")
            return {
                "city": None,
                "country": None,
                "confidence": 0.0,
                "error": str(e),
            }
