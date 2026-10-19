"""
DEPRECATED: This module is no longer used.

All city capability checks have been removed from the system.
ProviderManager now serves ANY query for ANY city without restrictions.
See ADAPTIVE_INTELLIGENCE_IMPLEMENTATION.md for architectural details.

This file is retained for historical reference only and can be safely deleted.
"""

from pydantic import BaseModel
from typing import Dict, Optional, List

class CityCapability(BaseModel):
    city_id: str
    country_code: str
    display_name: str
    capabilities: Dict[str, bool]
    providers: Dict[str, Optional[str]]
    partial_notes: Optional[Dict[str, str]] = None  # domain -> explanation for partial support


class CityCapabilityRegistry:
    def __init__(self):
        self._registry: Dict[str, CityCapability] = {
            # ── FULL SUPPORT ──
            "boston": CityCapability(
                city_id="boston", country_code="US", display_name="Boston",
                capabilities={"places": True, "transit": True, "events": True, "services": True, "work": True},
                providers={"places": "google_places", "transit": "mbta", "events": "eventbrite", "services": "osm_overpass"},
            ),
            # ── PLACES + SERVICES + EVENTS (no transit) ──
            "new york": CityCapability(
                city_id="new york", country_code="US", display_name="New York",
                capabilities={"places": True, "transit": False, "events": True, "services": True, "work": True},
                providers={"places": "google_places", "transit": None, "events": "eventbrite", "services": "osm_overpass"},
                partial_notes={"transit": "NYC transit provider not yet integrated. MTA integration planned."},
            ),
            "san francisco": CityCapability(
                city_id="san francisco", country_code="US", display_name="San Francisco",
                capabilities={"places": True, "transit": False, "events": True, "services": True, "work": True},
                providers={"places": "google_places", "transit": None, "events": "eventbrite", "services": "osm_overpass"},
                partial_notes={"transit": "BART/Muni provider not yet integrated."},
            ),
            "chicago": CityCapability(
                city_id="chicago", country_code="US", display_name="Chicago",
                capabilities={"places": True, "transit": False, "events": True, "services": True, "work": True},
                providers={"places": "google_places", "transit": None, "events": "eventbrite", "services": "osm_overpass"},
                partial_notes={"transit": "CTA provider not yet integrated."},
            ),
            "los angeles": CityCapability(
                city_id="los angeles", country_code="US", display_name="Los Angeles",
                capabilities={"places": True, "transit": False, "events": True, "services": True, "work": True},
                providers={"places": "google_places", "transit": None, "events": "eventbrite", "services": "osm_overpass"},
                partial_notes={"transit": "LA Metro provider not yet integrated."},
            ),
            # ── PLACES + SERVICES ONLY ──
            "london": CityCapability(
                city_id="london", country_code="GB", display_name="London",
                capabilities={"places": True, "transit": False, "events": False, "services": True, "work": True},
                providers={"places": "google_places", "transit": None, "events": None, "services": "osm_overpass"},
                partial_notes={
                    "transit": "TfL provider not yet integrated.",
                    "events": "No UK event provider integrated yet."
                },
            ),
            "toronto": CityCapability(
                city_id="toronto", country_code="CA", display_name="Toronto",
                capabilities={"places": True, "transit": False, "events": False, "services": True, "work": True},
                providers={"places": "google_places", "transit": None, "events": None, "services": "osm_overpass"},
                partial_notes={
                    "transit": "TTC provider not yet integrated.",
                    "events": "No CA event provider integrated yet."
                },
            ),
            "berlin": CityCapability(
                city_id="berlin", country_code="DE", display_name="Berlin",
                capabilities={"places": True, "transit": False, "events": False, "services": True, "work": True},
                providers={"places": "google_places", "transit": None, "events": None, "services": "osm_overpass"},
                partial_notes={
                    "transit": "BVG provider not yet integrated.",
                    "events": "No DE event provider integrated yet."
                },
            ),
            # ── PLACES ONLY ──
            "tokyo": CityCapability(
                city_id="tokyo", country_code="JP", display_name="Tokyo",
                capabilities={"places": True, "transit": False, "events": False, "services": False, "work": True},
                providers={"places": "google_places", "transit": None, "events": None, "services": None},
                partial_notes={
                    "transit": "Tokyo Metro provider not yet integrated.",
                    "events": "No JP event provider integrated yet.",
                    "services": "OSM coverage for Tokyo services is limited."
                },
            ),
            "mumbai": CityCapability(
                city_id="mumbai", country_code="IN", display_name="Mumbai",
                capabilities={"places": True, "transit": False, "events": False, "services": False, "work": True},
                providers={"places": "google_places", "transit": None, "events": None, "services": None},
                partial_notes={
                    "transit": "Mumbai Metro provider not yet integrated.",
                    "events": "No IN event provider integrated yet.",
                    "services": "OSM coverage for Mumbai services is limited."
                },
            ),
        }

    def get_capabilities(self, city: str) -> CityCapability:
        normalized = city.lower().strip() if city else ""
        if normalized in self._registry:
            return self._registry[normalized]

        # Unknown city — places + work via Google, nothing else
        return CityCapability(
            city_id=normalized,
            country_code="",
            display_name=city.strip() if city else "Unknown",
            capabilities={"places": True, "transit": False, "events": False, "services": False, "work": True},
            providers={"places": "google_places", "transit": None, "events": None, "services": None},
            partial_notes={
                "transit": "No transit provider available for this city.",
                "events": "No event provider available for this city.",
                "services": "No services provider available for this city."
            },
        )

    def list_cities(self) -> List[Dict]:
        return [
            {
                "city_id": c.city_id,
                "display_name": c.display_name,
                "country_code": c.country_code,
                "support_level": self._support_level(c),
                "capabilities": c.capabilities,
            }
            for c in self._registry.values()
        ]

    @staticmethod
    def _support_level(cap: CityCapability) -> str:
        active = sum(1 for v in cap.capabilities.values() if v)
        if active >= 5:
            return "full"
        if active >= 3:
            return "high"
        if active >= 2:
            return "partial"
        return "minimal"
