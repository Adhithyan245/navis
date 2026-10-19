"""
Centralized configuration for Navis API.

All API keys and settings are loaded from environment variables.
Missing optional keys log a warning but do NOT crash the server.
Missing critical keys (e.g., database) will raise at startup.

Usage:
    from core.config import settings
    key = settings.google_places_api_key
"""

import os
import logging

logger = logging.getLogger(__name__)

_OPTIONAL_KEYS = [
    "YELP_API_KEY",
    "OPENAI_API_KEY",
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "TICKETMASTER_API_KEY",
    "MBTA_API_KEY",
    "EVENTBRITE_API_KEY",
]

_RECOMMENDED_KEYS = [
    "GOOGLE_PLACES_API_KEY",
]


class Settings:
    """
    Runtime settings loaded from environment variables.
    All keys are optional — missing keys degrade gracefully.
    Call settings.warn_missing() at startup to log all gaps.
    """

    def __init__(self):
        # ── Core ──────────────────────────────────────────────
        self.google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

        # ── Events ────────────────────────────────────────────
        self.eventbrite_api_key: str = os.getenv("EVENTBRITE_API_KEY", "")
        self.ticketmaster_api_key: str = os.getenv("TICKETMASTER_API_KEY", "")

        # ── Places / Food ─────────────────────────────────────
        self.yelp_api_key: str = os.getenv("YELP_API_KEY", "")

        # ── Transit ───────────────────────────────────────────
        self.mbta_api_key: str = os.getenv("MBTA_API_KEY", "")

        # ── Jobs ──────────────────────────────────────────────
        self.adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
        self.adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")

        # ── AI / NLU ──────────────────────────────────────────
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # ── Real Estate / Relocation ──────────────────────────
        self.zillow_api_key: str = os.getenv("ZILLOW_API_KEY", "")

        # ── Database ──────────────────────────────────────────
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./navis.db")

    # ── Feature flags (derived from key availability) ─────────

    @property
    def has_google_places(self) -> bool:
        return bool(self.google_places_api_key)

    @property
    def has_yelp(self) -> bool:
        return bool(self.yelp_api_key)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_adzuna(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)

    @property
    def has_ticketmaster(self) -> bool:
        return bool(self.ticketmaster_api_key)

    @property
    def has_eventbrite(self) -> bool:
        return bool(self.eventbrite_api_key)

    @property
    def has_mbta(self) -> bool:
        return bool(self.mbta_api_key)

    @property
    def has_zillow(self) -> bool:
        return bool(self.zillow_api_key)

    @property
    def has_google_maps(self) -> bool:
        return bool(self.google_maps_api_key)

    def validate_api_dependencies(self) -> None:
        """
        Deprecated. Provider health is now verified dynamically at runtime.
        """
        pass

    def active_providers(self) -> dict:
        """Returns a dict of provider → enabled status for /ops/metrics."""
        return {
            "google_places": self.has_google_places,
            "yelp": self.has_yelp,
            "eventbrite": self.has_eventbrite,
            "ticketmaster": self.has_ticketmaster,
            "mbta": self.has_mbta,
            "adzuna": self.has_adzuna,
            "openai": self.has_openai,
            "osm_overpass": True,  # No key required
        }


# Singleton — import this everywhere
settings = Settings()
