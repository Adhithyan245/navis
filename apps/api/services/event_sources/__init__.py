"""Tech & community event sources merged by EventsService (see base.py)."""
from apps.api.services.event_sources.base import EventSource, SourceQuery
from apps.api.services.event_sources.devevents import DevEventsSource
from apps.api.services.event_sources.devpost import DevpostSource
from apps.api.services.event_sources.luma import LumaSource
from apps.api.services.event_sources.mlh import MLHSource

TECH_SOURCES: tuple[EventSource, ...] = (LumaSource(), DevpostSource(), MLHSource(), DevEventsSource())

__all__ = ["EventSource", "SourceQuery", "TECH_SOURCES"]
