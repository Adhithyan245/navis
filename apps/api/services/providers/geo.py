from typing import Optional
from urllib.parse import quote

import aiohttp
from apps.api.services.providers.base import BaseProvider
from apps.api.observability.circuit_breaker import circuit_breaker
from apps.api.services.cache.ttl_cache import ttl_cache
from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.services.place_extraction import MAX_PLACE_LEN as _MAX_GEO_QUERY_LEN, extract_place, is_activity_query

logger = get_logger(__name__)


# Geocoders expect address-like input. A full conversational sentence
# fuzzy-matches against random POIs whose names contain user-supplied words
# (e.g. "good place" → a river in Sumatra named "...good place to chill...").
# Place extraction (services/place_extraction.py) plus these thresholds are
# the only sanitization applied.
_MIN_GEO_IMPORTANCE = 0.4   # Nominatim: cities ≈0.7+, towns 0.4-0.6, POIs <0.3
_MIN_GEOAPIFY_CONFIDENCE = 0.5


def _sanitize_geo_query(raw: str) -> str:
    """Reduce a conversational query to its most likely location phrase."""
    return extract_place(raw)


class GeoProvider(BaseProvider):
    @ttl_cache(ttl=86400)
    @circuit_breaker(threshold=3, timeout=30)
    async def fetch(self, query: str, city: Optional[str] = None) -> dict:
        sanitized = _sanitize_geo_query(query)
        if sanitized != query:
            logger.info("geo.query.sanitized", original=query, sanitized=sanitized)

        # "good brunch spots" names no place: anchor on the user's city
        # instead of geocoding the sentence.
        if city and city.strip() and is_activity_query(query):
            hit = await self._lookup(city.strip()) or await self._service_lookup(city.strip())
            if hit:
                return hit

        # Fallback chain, most specific first: the extracted place, the same
        # text through the fuzzy multi-provider search, its trailing place
        # name ("Old Harbour Reykjavik" → "Reykjavik"), then the user's city.
        hit = await self._lookup(sanitized)
        if hit:
            return hit
        hit = await self._service_lookup(sanitized)
        if hit:
            return hit
        words = sanitized.split()
        for n in (2, 1):
            if len(words) > n:
                hit = await self._lookup(" ".join(words[-n:]))
                if hit:
                    return hit
        if city and city.strip() and city.strip().lower() != sanitized.lower():
            hit = await self._lookup(city.strip()) or await self._service_lookup(city.strip())
            if hit:
                logger.info("geo.fallback.city", query=sanitized, city=city)
                return hit
        raise ValueError("Both Nominatim and Geoapify failed to return data.")

    async def _service_lookup(self, text: str) -> Optional[dict]:
        from apps.api.services.geocoding import geocoding_service
        try:
            matches = await geocoding_service.search(text, limit=1)
        except Exception:  # noqa: BLE001
            return None
        if not matches:
            return None
        m = matches[0]
        return {"lat": str(m.lat), "lon": str(m.lon), "name": m.label}

    async def _lookup(self, sanitized: str) -> Optional[dict]:
        # Nominatim Primary
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12, connect=5)) as session:
            url = f"https://nominatim.openstreetmap.org/search?q={quote(sanitized)}&format=json&limit=5"
            headers = {"User-Agent": "NavisOrchestrator/1.0"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Reject low-importance fuzzy POI matches. Real cities/towns
                    # score >= 0.4; anything lower is usually a random POI whose
                    # name happens to contain a user word.
                    strong = [
                        r for r in (data or [])
                        if float(r.get("importance", 0) or 0) >= _MIN_GEO_IMPORTANCE
                    ]
                    if strong:
                        return {
                            "lat": strong[0]["lat"],
                            "lon": strong[0]["lon"],
                            "name": strong[0]["display_name"],
                        }
                    if data:
                        logger.warning(
                            "geo.nominatim.weak_only",
                            query=sanitized,
                            candidates=len(data),
                            top_importance=max(
                                (float(r.get("importance", 0) or 0) for r in data),
                                default=0.0,
                            ),
                        )

                # Fallback to Geoapify if Nominatim returned nothing strong
                if settings.GEOAPIFY_API_KEY:
                    geoapify_url = (
                        f"https://api.geoapify.com/v1/geocode/search?text={quote(sanitized)}"
                        f"&limit=5&apiKey={settings.GEOAPIFY_API_KEY}"
                    )
                    async with session.get(geoapify_url) as fb_resp:
                        if fb_resp.status == 200:
                            fb_data = await fb_resp.json()
                            for feat in fb_data.get("features", []) or []:
                                props = feat.get("properties", {}) or {}
                                rank = props.get("rank", {}) or {}
                                confidence = float(rank.get("confidence", 0) or 0)
                                if confidence < _MIN_GEOAPIFY_CONFIDENCE:
                                    continue
                                if "lat" in props and "lon" in props:
                                    return {
                                        "lat": props["lat"],
                                        "lon": props["lon"],
                                        "name": props.get("formatted", sanitized),
                                    }
        return None
