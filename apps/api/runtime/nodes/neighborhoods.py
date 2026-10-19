"""
NeighborhoodCandidatesNode — dynamic, worldwide neighborhood candidate
generation. Backs the `neighborhood_match` workflow (no corpus/markdown).

Config:

  type: neighborhood_candidates
  config:
    location: ${ctx.user.cityLocation}        # resolved Location dict (preferred)
    city: ${ctx.user.city}                     # text fallback if no Location
    office: ${ctx.user.officeLocationResolved} # optional Location dict
    commute_modes: [driving]                    # optional; modes for summaries
    limit: 20

Returns: {"city": <center Location dict | None>, "candidates": [Location dict, ...]}

When an office location is available, each candidate dict gains a lightweight
`commutes` list ({mode, durationMinutes, distanceKm}) via the shared
RoutingService. Routing is best-effort: a candidate with no successful route
simply carries an empty `commutes` list — it is still returned. Each candidate
is otherwise a canonical Location. Failure is soft throughout.
"""
from __future__ import annotations

import asyncio
from typing import Any, List, Optional, Tuple

from apps.api.models.commute import CommuteSummary
from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.geo_common import center_radius_m, resolve_center
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.geocoding import geocoding_service
from apps.api.services.routing import SUPPORTED_MODES, routing_service


@register("neighborhood_candidates")
class NeighborhoodCandidatesNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config
        limit = int(cfg.get("limit", 20))

        center = await resolve_center(cfg, ctx)
        if center is None:
            return {"city": None, "candidates": []}

        candidates = await geocoding_service.nearby_areas(
            float(center["lat"]),
            float(center["lon"]),
            radius_m=center_radius_m(center),
            limit=limit,
            bbox=center.get("bbox"),
        )
        candidate_dicts = [c.model_dump() for c in candidates]

        office = await self._coerce_office(resolve(cfg.get("office"), ctx))
        if office is not None:
            await self._attach_commutes(candidate_dicts, office, self._modes(cfg))

        return {"city": center, "candidates": candidate_dicts}

    def _modes(self, cfg: dict) -> List[str]:
        raw = cfg.get("commute_modes")
        if isinstance(raw, (list, tuple)):
            valid = [
                str(m).strip().lower()
                for m in raw
                if str(m).strip().lower() in SUPPORTED_MODES
            ]
            if valid:
                return valid
        return ["driving"]

    async def _coerce_office(self, val: Any) -> Optional[Tuple[float, float]]:
        if (
            isinstance(val, dict)
            and val.get("lat") is not None
            and val.get("lon") is not None
        ):
            try:
                return float(val["lat"]), float(val["lon"])
            except (TypeError, ValueError):
                return None
        if isinstance(val, str) and val.strip():
            matches = await geocoding_service.search(val.strip(), limit=1)
            if matches:
                return matches[0].lat, matches[0].lon
        return None

    async def _attach_commutes(
        self,
        candidates: List[dict],
        office: Tuple[float, float],
        modes: List[str],
    ) -> None:
        office_lat, office_lon = office

        async def summarize(cand: dict) -> None:
            lat = cand.get("lat")
            lon = cand.get("lon")
            summaries: List[dict] = []
            if lat is not None and lon is not None:
                for mode in modes:
                    leg = await routing_service.route(
                        float(lat), float(lon), office_lat, office_lon, mode
                    )
                    if leg is not None:
                        summaries.append(
                            CommuteSummary(
                                mode=mode,
                                duration_minutes=leg.duration_minutes,
                                distance_km=leg.distance_km,
                            ).model_dump(by_alias=True)
                        )
            cand["commutes"] = summaries

        await asyncio.gather(*(summarize(c) for c in candidates))
