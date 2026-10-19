import asyncio
from typing import Optional
from aiohttp import ClientSession
from apps.api.core.config import settings
from apps.api.services.providers.geo import GeoProvider
from apps.api.services.providers.places import PlacesProvider
from apps.api.services.providers.transit import TransitProvider
from apps.api.services.providers.events import EventsProvider
from apps.api.services.providers.wiki import WikiProvider
from apps.api.services.providers.ai import AIProvider

class ProviderManager:
    """Dependency injection manager for all providers."""
    
    def __init__(self):
        self._geo = GeoProvider()
        self._places = PlacesProvider()
        self._transit = TransitProvider()
        self._events = EventsProvider()
        self._wiki = WikiProvider()
        self._ai = AIProvider()
        
        self.session: Optional[ClientSession] = None
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)

    def set_session(self, session: ClientSession):
        self.session = session
        # Inject session into all providers
        self._geo.session = session
        self._places.session = session
        self._transit.session = session
        self._events.session = session
        self._wiki.session = session
        self._ai.session = session

    @property
    def geo(self) -> GeoProvider:
        return self._geo

    @property
    def places(self) -> PlacesProvider:
        return self._places

    @property
    def transit(self) -> TransitProvider:
        return self._transit

    @property
    def events(self) -> EventsProvider:
        return self._events

    @property
    def wiki(self) -> WikiProvider:
        return self._wiki

    @property
    def ai(self) -> AIProvider:
        return self._ai

provider_manager = ProviderManager()
