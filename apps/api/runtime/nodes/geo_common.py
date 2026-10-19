"""
Shared helpers for geospatial nodes (neighborhood_candidates, city_explore).

Keeps center-location resolution in one place so the discovery nodes don't
duplicate it.
"""
from __future__ import annotations

from typing import Optional

from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.geocoding import _bbox_radius_m, geocoding_service

DEFAULT_RADIUS_M = 10_000.0


async def resolve_center(cfg: dict, ctx: NodeContext) -> Optional[dict]:
    """
    Resolve the search-center Location dict for a discovery node.

    Order:
      1. `location` config (a pre-resolved Location dict, e.g. profile.cityLocation).
      2. geocode `city` text.
      3. geocode `ctx.query`.

    Returns the Location as a plain dict, or None when nothing resolves.
    """
    loc_ref = resolve(cfg.get("location"), ctx) if cfg.get("location") else None
    if (
        isinstance(loc_ref, dict)
        and loc_ref.get("lat") is not None
        and loc_ref.get("lon") is not None
    ):
        return loc_ref

    text = resolve(cfg.get("city"), ctx) if cfg.get("city") else None
    if isinstance(text, (list, tuple)):
        text = next((str(t) for t in text if t), "")
    text = str(text or "").strip() or ctx.query
    if not text:
        return None

    matches = await geocoding_service.search(text, limit=1)
    return matches[0].model_dump() if matches else None


def center_radius_m(center: dict) -> float:
    """Search radius for a resolved center: derived from its bbox, else default."""
    return _bbox_radius_m(center.get("bbox")) or DEFAULT_RADIUS_M
