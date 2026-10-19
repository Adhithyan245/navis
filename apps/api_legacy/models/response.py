import re
import logging
from pydantic import BaseModel, field_validator
from typing import Dict, Any, List, Optional, Literal, Union

logger = logging.getLogger(__name__)

# Known source identifiers — used for logging unknown sources.
KNOWN_SOURCES = {
    "google_places", "mbta", "eventbrite", "osm_overpass",
    "user_events_db", "saved_items_db", "user_profiles_db",
    "settle_tasks_db", "yelp", "ticketmaster", "adzuna",
    "openai_gpt", "openai_whisper", "cms_npi", "zillow",
    "google_maps", "nominatim", "osrm", "ollama"
}

_SOURCE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

class APIResponse(BaseModel):
    # --- STRICT API CONTRACT ---
    status: Literal["success", "fallback", "error"]
    agent: str = "unknown"
    source: str = "unknown"
    data: Union[List, Dict]
    trace_id: str = "unknown"
    latency_ms: int = 0
    message: Optional[str] = None
    reason: Optional[str] = None
    
    # --- DEPRECATED FIELDS (Compatibility Mode) ---
    explanation: Optional[str] = None
    context_used: Optional[Dict[str, Any]] = None
    sources: Optional[List[str]] = None
    source_mode: Optional[str] = None
    suggestions: Optional[List[str]] = None


    @field_validator("sources")
    @classmethod
    def validate_source_identifiers(cls, v):
        if v is None:
            return v
        for s in v:
            if not _SOURCE_PATTERN.match(s):
                raise ValueError(
                    f"Source identifier '{s}' must be lowercase snake_case (e.g. 'google_places')."
                )
            if s not in KNOWN_SOURCES:
                logger.warning(
                    "Unknown source identifier '%s' — add to KNOWN_SOURCES in models/response.py "
                    "if this is a new intentional provider.", s
                )
        return v

    @field_validator("source_mode")
    @classmethod
    def validate_source_mode_consistency(cls, v, info):
        if v is None:
            return v
        sources = info.data.get("sources", []) or []
        status = info.data.get("status", "")
        if status == "fallback" and v != "fallback":
            raise ValueError(f"source_mode must be 'fallback' when status is 'fallback', got '{v}'")
        if not sources and status != "fallback" and v == "live":
            raise ValueError("source_mode cannot be 'live' with empty sources unless status is fallback")
        return v

