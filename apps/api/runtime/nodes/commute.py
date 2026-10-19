"""
CommuteNode — estimates travel time/distance from an origin to a destination
across one or more modes (driving / walking / cycling), via the provider-
agnostic RoutingService.

Config:

  type: commute
  config:
    origin: ${ctx.user.origin}            # Location dict (preferred) or text
    destination: ${ctx.user.destination}  # Location dict (preferred) or text
    modes: [driving, walking, cycling]    # optional; defaults to all three

Returns: {"origin": <Location dict|None>, "destination": <Location dict|None>,
          "commutes": [CommuteEstimate dict, ...]}

Failure is soft — missing/unresolvable endpoints or provider errors yield an
empty `commutes` list rather than failing the workflow.
"""
from __future__ import annotations

from typing import Any, List, Optional

from apps.api.models.commute import CommuteEstimate
from apps.api.models.location import Location
from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.geocoding import geocoding_service
from apps.api.services.place_extraction import extract_route
from apps.api.services.routing import SUPPORTED_MODES, routing_service


@register("commute")
class CommuteNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config

        origin_val = resolve(cfg.get("origin"), ctx)
        destination_val = resolve(cfg.get("destination"), ctx)

        # Free-text commute questions ("from Back Bay to Kendall Square")
        # arrive without structured endpoints; pull them from the query.
        if not origin_val or not destination_val:
            route = extract_route(ctx.query or "")
            if route:
                origin_val = origin_val or route[0]
                destination_val = destination_val or route[1]

        # Text endpoints are geocoded near the user's city, so "Kendall
        # Square" resolves to the one in Cambridge, not a street elsewhere.
        bias, city = await self._city_bias(ctx)
        origin = await self._coerce_location(origin_val, bias, city)
        destination = await self._coerce_location(destination_val, bias, city)
        if origin is None or destination is None:
            return {
                "origin": origin.model_dump() if origin else None,
                "destination": destination.model_dump() if destination else None,
                "commutes": [],
            }

        modes = self._modes(cfg)
        commutes: List[dict] = []
        for mode in modes:
            leg = await routing_service.route(
                origin.lat, origin.lon, destination.lat, destination.lon, mode
            )
            if leg is None:
                continue
            estimate = CommuteEstimate(
                origin=origin,
                destination=destination,
                distance_km=leg.distance_km,
                duration_minutes=leg.duration_minutes,
                mode=mode,
                provider=leg.provider,
                confidence=leg.confidence,
            )
            commutes.append(estimate.model_dump(by_alias=True))

        return {
            "origin": origin.model_dump(),
            "destination": destination.model_dump(),
            "commutes": commutes,
        }

    def _modes(self, cfg: dict) -> List[str]:
        raw = cfg.get("modes")
        if isinstance(raw, (list, tuple)):
            modes = [str(m).strip().lower() for m in raw if m]
            valid = [m for m in modes if m in SUPPORTED_MODES]
            if valid:
                return valid
        return list(SUPPORTED_MODES)

    async def _city_bias(self, ctx: NodeContext) -> tuple:
        """(lat, lon) of the user's city, or None; plus the city name."""
        uc = ctx.user_context if isinstance(ctx.user_context, dict) else {}
        city = uc.get("city") if isinstance(uc.get("city"), str) else None
        loc = uc.get("cityLocation")
        if isinstance(loc, dict) and loc.get("lat") is not None and loc.get("lon") is not None:
            try:
                return (float(loc["lat"]), float(loc["lon"])), city
            except (TypeError, ValueError):
                pass
        if city and city.strip():
            matches = await geocoding_service.search(city.strip(), limit=1)
            if matches:
                return (matches[0].lat, matches[0].lon), city
        return None, city

    async def _coerce_location(
        self, val: Any, bias: Optional[tuple] = None, city: Optional[str] = None
    ) -> Optional[Location]:
        if isinstance(val, dict) and val.get("lat") is not None and val.get("lon") is not None:
            try:
                return Location.model_validate(val)
            except Exception:  # noqa: BLE001
                return None
        if isinstance(val, str) and val.strip():
            matches = await geocoding_service.search(
                val.strip(), limit=1,
                bias_lat=bias[0] if bias else None,
                bias_lon=bias[1] if bias else None,
                city=city,
            )
            return matches[0] if matches else None
        return None
