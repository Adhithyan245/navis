"""
Commute model — a single origin→destination travel estimate for one mode.

Serializes with camelCase aliases (distanceKm / durationMinutes) so the wire
shape matches the frontend Commute interface directly, with no mapping layer.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from apps.api.models.location import Location


class CommuteEstimate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    origin: Location
    destination: Location
    distance_km: float = Field(serialization_alias="distanceKm")
    duration_minutes: float = Field(serialization_alias="durationMinutes")
    mode: str
    provider: str
    confidence: float = 0.0


class CommuteSummary(BaseModel):
    """Lightweight per-candidate commute leg (no origin/destination/provider).

    Attached to neighborhood candidates so future ranking systems can consume
    commute data without a schema change.
    """
    model_config = ConfigDict(populate_by_name=True)

    mode: str
    duration_minutes: float = Field(serialization_alias="durationMinutes")
    distance_km: float = Field(serialization_alias="distanceKm")
