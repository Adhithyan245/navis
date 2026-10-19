"""
Provider layer for Navis backend.

All external data access (APIs, databases, services) flows through providers.
Each provider is defensive and never returns None.
"""

from .base import BaseProvider, ProviderCapability, ProviderRegistry
from .geo import GeoProvider
from .places import PlacesProvider
from .transit import TransitProvider
from .events import EventsProvider
from .wiki import WikiProvider

__all__ = [
    "BaseProvider",
    "ProviderCapability",
    "ProviderRegistry",
    "GeoProvider",
    "PlacesProvider",
    "TransitProvider",
    "EventsProvider",
    "WikiProvider",
]
