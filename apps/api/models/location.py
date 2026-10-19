"""
Canonical Location model — the provider-agnostic representation of any
resolved place on Earth (country → coordinate).

Geocoding providers (Geoapify primary, Nominatim fallback) each return their
own feature shapes; the geocoding service normalizes both into this single
model so the rest of Navis (workflows, routes, frontend) never sees a
provider-specific payload.

This is additive infrastructure for Phase 3A. Existing workflows that use the
legacy GeoProvider are unaffected.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Coarse-to-fine place categories. Kept as a plain str on the model (not an
# enum) so unfamiliar provider result types degrade to "unknown" rather than
# raising — global coverage means we will see types we didn't enumerate.
LOCATION_TYPES = (
    "country",
    "region",       # state / province
    "county",
    "city",
    "district",
    "suburb",       # neighborhood-level
    "neighborhood",
    "street",
    "postcode",
    "landmark",     # amenity / POI / named feature
    "address",      # exact house/building
    "coordinate",   # raw lat/lon input, reverse-resolved
    "place",        # generic catch-all for an otherwise-unclassified feature
    "unknown",
)


class Location(BaseModel):
    """A single resolved place. `lat`/`lon` are always present."""

    id: str                                   # provider-prefixed stable id
    type: str = "unknown"                     # one of LOCATION_TYPES
    name: str                                 # short label ("Cambridge")
    label: str                                # full formatted display string
    lat: float
    lon: float
    bbox: Optional[List[float]] = None        # [minLon, minLat, maxLon, maxLat]

    # Administrative hierarchy (best-effort; any may be absent).
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    suburb: Optional[str] = None
    postcode: Optional[str] = None

    provider: str                             # "geoapify" | "nominatim"
    confidence: float = 0.0                   # 0..1, provider-reported when available

    # ── Optional enrichment (Phase 3B) ───────────────────────────────────────
    # Populated best-effort from the provider; absent fields degrade
    # gracefully. `region` remains the canonical state/province field; `state`
    # mirrors it for consumers that expect that name.
    state: Optional[str] = None
    short_description: Optional[str] = None
    population: Optional[int] = None
    tags: List[str] = Field(default_factory=list)

    raw: Dict[str, Any] = Field(default_factory=dict)
