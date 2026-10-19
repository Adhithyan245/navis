"""
Routing service — provider-agnostic travel-time estimation.

A `RoutingProvider` ABC defines the seam so engines (Geoapify, OpenRouteService,
future Valhalla/Google) can be swapped or chained without touching the commute
node or workflow. `RoutingService` tries providers in order and returns the
first successful `RouteLeg`.

Phase 4 Batch 1 supports three modes: driving, walking, cycling. No matrix, no
isochrones, no multi-stop — a single origin→destination leg per call.

Soft failure: a provider that errors or returns nothing is skipped; the
service returns None when no provider can answer, so callers degrade
gracefully.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

import aiohttp

from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import ttl_cache

logger = get_logger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=8.0)

# Canonical Navis modes. Providers map these to their own profile strings.
SUPPORTED_MODES = ("driving", "walking", "cycling")

_GEOAPIFY_MODE = {"driving": "drive", "walking": "walk", "cycling": "bicycle"}
_ORS_PROFILE = {
    "driving": "driving-car",
    "walking": "foot-walking",
    "cycling": "cycling-regular",
}


@dataclass(frozen=True)
class RouteLeg:
    distance_km: float
    duration_minutes: float
    provider: str
    confidence: float


class RoutingProvider(ABC):
    name: str = "routing"

    @abstractmethod
    async def route(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str,
    ) -> Optional[RouteLeg]:
        """Return a single-leg estimate, or None if unavailable for this mode."""


class GeoapifyRoutingProvider(RoutingProvider):
    name = "geoapify"

    async def route(
        self, *, origin_lat, origin_lon, dest_lat, dest_lon, mode
    ) -> Optional[RouteLeg]:
        key = settings.GEOAPIFY_API_KEY
        gmode = _GEOAPIFY_MODE.get(mode)
        if not key or not gmode:
            return None
        url = (
            "https://api.geoapify.com/v1/routing"
            f"?waypoints={origin_lat},{origin_lon}|{dest_lat},{dest_lon}"
            f"&mode={gmode}&apiKey={key}"
        )
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("routing.geoapify.bad_status", status=resp.status)
                        return None
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("routing.geoapify.error", error=str(exc))
            return None

        feats = data.get("features") or []
        if not feats:
            return None
        props = (feats[0] or {}).get("properties") or {}
        distance_m = props.get("distance")
        time_s = props.get("time")
        if distance_m is None or time_s is None:
            return None
        return RouteLeg(
            distance_km=round(float(distance_m) / 1000.0, 2),
            duration_minutes=round(float(time_s) / 60.0, 1),
            provider=self.name,
            confidence=0.9,
        )


class ORSRoutingProvider(RoutingProvider):
    name = "openrouteservice"

    async def route(
        self, *, origin_lat, origin_lon, dest_lat, dest_lon, mode
    ) -> Optional[RouteLeg]:
        key = settings.OPENROUTESERVICE_API_KEY
        profile = _ORS_PROFILE.get(mode)
        if not key or not profile:
            return None
        url = (
            f"https://api.openrouteservice.org/v2/directions/{profile}"
            f"?api_key={key}&start={origin_lon},{origin_lat}&end={dest_lon},{dest_lat}"
        )
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("routing.ors.bad_status", status=resp.status)
                        return None
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("routing.ors.error", error=str(exc))
            return None

        feats = data.get("features") or []
        if not feats:
            return None
        summary = (((feats[0] or {}).get("properties") or {}).get("summary") or {})
        distance_m = summary.get("distance")
        time_s = summary.get("duration")
        if distance_m is None or time_s is None:
            return None
        return RouteLeg(
            distance_km=round(float(distance_m) / 1000.0, 2),
            duration_minutes=round(float(time_s) / 60.0, 1),
            provider=self.name,
            confidence=0.85,
        )


class RoutingService:
    def __init__(self, providers: Optional[List[RoutingProvider]] = None) -> None:
        # Order = priority. Future engines slot in here, no node changes.
        self._providers = providers or [
            GeoapifyRoutingProvider(),
            ORSRoutingProvider(),
        ]

    @ttl_cache(ttl=21600)
    async def route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str,
    ) -> Optional[RouteLeg]:
        if mode not in SUPPORTED_MODES:
            return None
        for provider in self._providers:
            leg = await provider.route(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                mode=mode,
            )
            if leg is not None:
                return leg
        return None


# Module-level singleton; the commute node imports this.
routing_service = RoutingService()
