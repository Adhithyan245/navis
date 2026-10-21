"""
GeocodingService — universal, provider-agnostic location resolution.

Resolves arbitrary free text (country, city, district, neighborhood, street,
postcode, landmark, exact address) OR a raw "lat,lon" coordinate into one or
more canonical `Location` objects, worldwide.

Forward search (Google-Maps-like):
  1. Normalize the text (drop "Apt 3"/"#2B", expand "Sq"/"Ave"/"Stn"...).
  2. Geoapify search (fuzzy: tolerates typos) + autocomplete (partial words),
     biased toward the user's city when `bias_lat/bias_lon` are given.
  3. Nominatim with a local viewbox when results are weak or the query is
     an acronym — OSM short names resolve "MIT", "BU", "Logan".
     With a bias, Photon too: it surfaces the city's own neighbourhoods,
     stations and parks ("roxbury" → Roxbury, Roxbury Crossing) that
     same-named towns elsewhere would otherwise crowd out.
  4. For acronyms still unresolved, a fast LLM expands the token in the
     user's city context ("NEU" → "Northeastern University").
  5. Merge, dedupe, and rank by provider confidence + distance to the bias.
All providers are normalized into the same `Location` shape. This service is independent of the
legacy `GeoProvider` (which stays Nominatim-primary for explore/work
workflows) — nothing here changes existing behavior.

Design:
* `search(text, limit, autocomplete)` — forward geocode / autocomplete.
* `reverse(lat, lon)` — coordinate → place.
* Coordinate-looking input is detected and routed to reverse automatically.
* Results cached (TTL) — addresses are stable, so this cuts provider spend.
* Soft failure: providers that error are skipped; an empty list is returned
  rather than raising, so callers (route + node) can degrade gracefully.
"""
from __future__ import annotations

import asyncio
import math
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp

from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.services.cache.ttl_cache import cache, ttl_cache
from apps.api.services.geocode_query import expand_acronym, looks_like_acronym, normalize_query

logger = get_logger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=8.0)
_NOMINATIM_HEADERS = {"User-Agent": "NavisOrchestrator/1.0 (geocoding)"}
_MAX_TEXT_LEN = 120

# "12.97, 77.59" / "12.97 77.59" / "-33.8688,151.2093"
_COORD_RE = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)

# Geoapify result_type → canonical type. Unknown values fall through to the
# raw value if it is a known canonical type, else "unknown".
_GEOAPIFY_TYPE_MAP: Dict[str, str] = {
    "country": "country",
    "state": "region",
    "county": "county",
    "city": "city",
    "postcode": "postcode",
    "district": "district",
    "suburb": "suburb",
    "neighbourhood": "suburb",
    "street": "street",
    "amenity": "landmark",
    "building": "address",
    "house": "address",
}

# Nominatim addresstype/class → canonical type.
_NOMINATIM_TYPE_MAP: Dict[str, str] = {
    "country": "country",
    "state": "region",
    "region": "region",
    "county": "county",
    "city": "city",
    "town": "city",
    "village": "city",
    "municipality": "city",
    "city_district": "district",
    "district": "district",
    "suburb": "suburb",
    "neighbourhood": "suburb",
    "quarter": "suburb",
    "road": "street",
    "postcode": "postcode",
    "house": "address",
    "building": "address",
}


def _clamp_text(text: str) -> str:
    text = text.strip()
    return text[:_MAX_TEXT_LEN] if len(text) > _MAX_TEXT_LEN else text


def _coerce_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_int(v: Any) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _geoapify_population(props: Dict[str, Any]) -> Optional[int]:
    """Population is provider-optional: try the flat field, then the raw OSM tags."""
    pop = _coerce_int(props.get("population"))
    if pop is not None:
        return pop
    raw = ((props.get("datasource") or {}).get("raw") or {})
    return _coerce_int(raw.get("population"))


def _geoapify_place_tags(props: Dict[str, Any]) -> List[str]:
    """Readable tags from Geoapify place categories (strip the namespace prefix)."""
    tags: List[str] = []
    seen = set()
    for c in (props.get("categories") or []):
        label = str(c).split(".")[-1].replace("_", " ").strip()
        if label and label not in seen:
            seen.add(label)
            tags.append(label)
    return tags[:6]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _point_in_bbox(lat: float, lon: float, bbox: List[float], *, pad: float = 0.0) -> bool:
    """bbox = [minLon, minLat, maxLon, maxLat]. `pad` is a small degree margin."""
    if not bbox or len(bbox) != 4:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        (min_lon - pad) <= lon <= (max_lon + pad)
        and (min_lat - pad) <= lat <= (max_lat + pad)
    )


def _anchor_points(
    lat: float, lon: float, bbox: Optional[List[float]]
) -> List[tuple[float, float]]:
    """
    Multi-anchor coverage: the center plus four interior points pulled toward
    each bbox edge. Querying every anchor and merging gives uniform spatial
    coverage instead of a single-center query that misses far districts.
    """
    anchors = [(lat, lon)]
    if bbox and len(bbox) == 4:
        min_lon, min_lat, max_lon, max_lat = bbox
        dlat = (max_lat - min_lat) / 4.0
        dlon = (max_lon - min_lon) / 4.0
        if dlat > 0 and dlon > 0:
            anchors.extend([
                (lat + dlat, lon),  # north
                (lat - dlat, lon),  # south
                (lat, lon + dlon),  # east
                (lat, lon - dlon),  # west
            ])
    return anchors


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


_TOWN_TYPES = {"city", "county"}
_AREA_TYPES = {"suburb", "neighborhood", "district"}


def _dedup_locations(locs: List["Location"], *, area_radius_m: float = 350.0) -> List["Location"]:
    """
    Deduplicate by provider id, then by (normalized name + proximity): two
    results with the same normalized name within ~350m are the same place
    surfaced by different anchors/providers. Keeps the higher-confidence one.
    `area_radius_m` widens that radius for non-address results (campuses,
    airports, neighborhoods), whose points vary more between providers.
    """
    by_conf = sorted(locs, key=lambda l: l.confidence, reverse=True)
    kept: List["Location"] = []
    seen_ids: set = set()
    for loc in by_conf:
        if loc.id in seen_ids:
            continue
        name = _norm_name(loc.name)
        dup = False
        for k in kept:
            radius = 350.0 if loc.type in ("address", "street") else max(350.0, area_radius_m)
            places = _TOWN_TYPES | _AREA_TYPES
            if loc.type in places and k.type in places and (loc.type in _TOWN_TYPES or k.type in _TOWN_TYPES):
                # A town and its village centre ("Roxbury" / "Roxbury, Roxbury"),
                # or one city typed differently by two providers.
                radius = max(radius, 15_000.0)
            elif loc.type in _AREA_TYPES and k.type in _AREA_TYPES:
                radius = max(radius, 3_000.0)
            if _norm_name(k.name) == name and _haversine_m(k.lat, k.lon, loc.lat, loc.lon) <= radius:
                dup = True
                # The kept copy inherits what the others knew ("prominent", "expanded").
                k.tags = list(dict.fromkeys([*k.tags, *loc.tags]))
                break
        if dup:
            continue
        seen_ids.add(loc.id)
        kept.append(loc)
    return kept


def _bbox_radius_m(bbox: Optional[List[float]]) -> Optional[float]:
    """Approx radius (m) of the circle enclosing a [minLon,minLat,maxLon,maxLat] box."""
    if not bbox or len(bbox) != 4:
        return None
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_m = abs(max_lat - min_lat) * 111_000.0
    mid_lat = (min_lat + max_lat) / 2.0
    lon_m = abs(max_lon - min_lon) * 111_000.0 * math.cos(math.radians(mid_lat))
    return math.hypot(lat_m, lon_m) / 2.0


# OSM populated-place subtype → canonical Location type.
_PLACE_SUBTYPE_MAP = (
    ("neighbourhood", "neighborhood"),
    ("neighborhood", "neighborhood"),
    ("quarter", "suburb"),
    ("suburb", "suburb"),
    ("city_district", "district"),
    ("district", "district"),
    ("borough", "district"),
    ("town", "city"),
    ("village", "city"),
    ("hamlet", "city"),
    ("city", "city"),
)


class GeocodingService:
    # ── Public API ───────────────────────────────────────────────────────────
    async def search(
        self,
        text: str,
        *,
        limit: int = 5,
        autocomplete: bool = False,
        bias_lat: Optional[float] = None,
        bias_lon: Optional[float] = None,
        city: Optional[str] = None,
    ) -> List["Location"]:
        """Forward geocode. `bias_*` (the user's city centre) ranks nearby
        matches first, the way Google Maps prefers places near you; `city`
        gives acronym expansion its context."""
        text = _clamp_text(text or "")
        if not text:
            return []

        coord = _COORD_RE.match(text)
        if coord:
            lat = _coerce_float(coord.group(1))
            lon = _coerce_float(coord.group(2))
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                loc = await self.reverse(lat, lon)
                return [loc] if loc else []

        bias = None
        if bias_lat is not None and bias_lon is not None:
            if -90 <= bias_lat <= 90 and -180 <= bias_lon <= 180:
                bias = (round(bias_lat, 2), round(bias_lon, 2))
        limit = max(1, min(limit, 10))

        key = f"geocode.forward:{text.lower()}:{limit}:{autocomplete}:{bias}:{(city or '').lower()}"
        cached = await cache.get(key)
        if cached is not None:
            return cached
        results = await self._forward(text, limit=limit, autocomplete=autocomplete,
                                      bias=bias, city=city)
        if results:  # don't cache misses — they're often transient
            await cache.set(key, results, ttl=86400)
        return results

    async def _forward(
        self,
        text: str,
        *,
        limit: int,
        autocomplete: bool,
        bias: Optional[tuple] = None,
        city: Optional[str] = None,
    ) -> List["Location"]:
        query = normalize_query(text) or text
        acronym = looks_like_acronym(text)
        fetch = max(limit, 8)
        photon_task = prominent_task = None
        if bias is not None:
            photon_task = asyncio.create_task(_with_timeout(self._photon_forward(query, limit=fetch, bias=bias),
                                                            _PHOTON_TIMEOUT_S))
            # Unbiased, the world's best matches ("paris" → Paris, France), so
            # local streets can't push them off the list.
            prominent_task = asyncio.create_task(_with_timeout(self._photon_forward(query, limit=3, bias=None),
                                                               _PHOTON_TIMEOUT_S))

        # Typed-in-capitals acronyms ("NEU") always need OSM + expansion, so
        # start those right away instead of after Geoapify answers.
        nominatim_task = expand_task = None
        if acronym:
            nominatim_task = asyncio.create_task(self._nominatim_forward(query, limit=fetch, bias=bias))
            if text.strip().isupper():
                expand_task = asyncio.create_task(expand_acronym(text, city))

        # Geoapify search is fuzzy ("huntingon ave" → Huntington Avenue) and
        # handles full addresses; autocomplete adds partial-word matches
        # while the user is still typing.
        calls = [self._geoapify_forward(query, limit=fetch, autocomplete=False, bias=bias)]
        if autocomplete:
            calls.append(self._geoapify_forward(query, limit=fetch, autocomplete=True, bias=bias))
        if acronym:
            # Literal spelling matches of an acronym ("Neu-Ulm") rarely help;
            # don't let a slow Geoapify hold up the expansion.
            calls = [_with_timeout(c, _ACRONYM_GEOAPIFY_TIMEOUT_S) for c in calls]
        batches = await asyncio.gather(*calls)
        results: List["Location"] = [loc for batch in batches for loc in batch]
        prominent: List["Location"] = []
        if photon_task is not None:
            results += await photon_task
            prominent = await prominent_task
            for loc in prominent:
                loc.tags = list(dict.fromkeys([*loc.tags, "prominent"]))
            results += prominent

        # OSM knows aliases (short_name "MIT", alt_name "Southie") that
        # Geoapify's index doesn't; ask it when nothing matched by name.
        if nominatim_task is not None:
            results += await nominatim_task
        elif self._weak(results, bias) or not self._has_exact(results, query, bias):
            results += await self._nominatim_forward(query, limit=fetch, bias=bias)

        if expand_task is None and acronym and self._weak(results, bias):
            expand_task = asyncio.create_task(expand_acronym(text, city))

        expanded: List["Location"] = []
        if expand_task is not None:
            expansion = await expand_task
            if expansion:
                # Nominatim answers a full name in well under a second;
                # Geoapify is the fallback when it's busy or misses.
                expanded = await self._nominatim_forward(expansion, limit=3, bias=bias)
                if not expanded:
                    expanded = await self._geoapify_forward(expansion, limit=3, autocomplete=False, bias=bias)
                for loc in expanded:
                    loc.tags = list(dict.fromkeys([*loc.tags, "expanded"]))

        # Providers put a campus or airport's point in different spots, so
        # same-named non-address results within 2 km are one place.
        ranked = self._rank(_dedup_locations(results, area_radius_m=2000.0), bias=bias, query=query)
        if expanded:
            # The expansion is what the user meant ("NEU" → Northeastern
            # University); show it ahead of literal spelling matches.
            top = self._rank(_dedup_locations(expanded, area_radius_m=2000.0), bias=bias, query=query)[:1]
            ranked = [r for r in ranked
                      if not (_norm_name(r.name) == _norm_name(top[0].name)
                              and _haversine_m(r.lat, r.lon, top[0].lat, top[0].lon) <= 2000.0)]
            ranked = top + [r for r in ranked if r.id != top[0].id]
        return self._keep_prominent(ranked, bias=bias, query=query, limit=limit)

    @staticmethod
    def _keep_prominent(ranked: List["Location"], *, bias: Optional[tuple], query: str, limit: int) -> List["Location"]:
        """With a bias, local results win the ranking, but a far place named
        exactly like the query still belongs on the list (two slots). It goes
        first when nothing nearby is an area or town by that name."""
        if bias is None:
            return ranked[:limit]
        q = _norm_name(query)

        def far(r: "Location") -> bool:
            return _haversine_m(bias[0], bias[1], r.lat, r.lon) > 150_000

        exact_far = [r for r in ranked if _norm_name(r.name) == q and far(r)]
        # A country or region by that name first ("jamaica"), then what's
        # prominent worldwide, then provider confidence.
        exact_far.sort(key=lambda r: ({"country": 0, "region": 1}.get(r.type, 2),
                                      "prominent" not in r.tags, -float(r.confidence or 0.0)))
        picks = exact_far[:2]
        if not picks:
            return ranked[:limit]
        local_named = any(not far(r) and (q in _alias_names(r) or (
                              _norm_name(r.name) == q and r.type in _AREA_TYPES | _TOWN_TYPES | {"landmark"}))
                          for r in ranked)
        rest = [r for r in ranked if r not in picks][: limit - len(picks)]
        if local_named:
            # Keep the ranking's order; the picks only reclaim their places.
            keep = {id(r) for r in rest + picks}
            return [r for r in ranked if id(r) in keep][:limit]
        return picks + rest

    @staticmethod
    def _weak(results: List["Location"], bias: Optional[tuple]) -> bool:
        """No results, or (with a bias) nothing within ~80 km of it."""
        if not results:
            return True
        if bias is None:
            return max(r.confidence for r in results) < 0.6
        return not any(_haversine_m(bias[0], bias[1], r.lat, r.lon) <= 80_000 for r in results)

    @staticmethod
    def _has_exact(results: List["Location"], query: str, bias: Optional[tuple] = None) -> bool:
        """A result (near the bias, when given) is named exactly like the
        query, or — for addresses and streets — its label starts with it."""
        q = _norm_name(query)
        for r in results:
            if bias is not None and _haversine_m(bias[0], bias[1], r.lat, r.lon) > 80_000:
                continue
            if _norm_name(r.name) == q:
                return True
            if r.type in ("address", "street") and _norm_name(r.label).startswith(q):
                return True
        return False

    @staticmethod
    def _rank(results: List["Location"], *, bias: Optional[tuple], query: str) -> List["Location"]:
        """Provider confidence + proximity to the bias + name/alias match bonus."""
        q = _norm_name(query)

        def score(loc: "Location") -> float:
            s = float(loc.confidence or 0.0)
            if loc.provider == "nominatim":
                # Nominatim reports "importance", which runs far lower than
                # Geoapify's match confidence for the same quality of match.
                s = max(s, 0.5)
            if bias is not None:
                d = _haversine_m(bias[0], bias[1], loc.lat, loc.lon)
                if d <= 15_000:
                    s += 1.0
                elif d <= 50_000:
                    s += 0.7
                elif d <= 150_000:
                    s += 0.3
                # Tie-break equal matches by closeness (the same street name
                # in two suburbs 10 km apart).
                s += 0.2 * (1.0 - min(d, 50_000.0) / 50_000.0)
            name = _norm_name(loc.name)
            # A neighbourhood or town is usually what a short query means;
            # a street that merely starts with it is a weaker guess.
            if loc.type in _AREA_TYPES:
                s += 0.3
            elif loc.type in _TOWN_TYPES:
                s += 0.15
            elif loc.type in ("street", "address") and name != q:
                s -= 0.15
            # "12 Westland Ave" → that street's addresses; a one-word name
            # ("roxbury") shouldn't make every Roxbury Street an exact match.
            addressy = any(ch.isdigit() for ch in q) or " " in q
            if q and (name == q or (loc.type in ("address", "street") and addressy
                                     and _norm_name(loc.label).startswith(q))):
                s += 0.6
            elif q and name.startswith(q):
                s += 0.3  # "Logan" → "Logan International Airport"
            if q and q in _alias_names(loc):
                # The query is one of this place's official aliases.
                s += 1.0
            return s

        return sorted(results, key=score, reverse=True)

    @ttl_cache(ttl=86400)
    async def reverse(self, lat: float, lon: float) -> Optional["Location"]:
        loc = await self._geoapify_reverse(lat, lon)
        if loc:
            return loc
        return await self._nominatim_reverse(lat, lon)

    @ttl_cache(ttl=43200)
    async def nearby_areas(
        self,
        lat: float,
        lon: float,
        *,
        radius_m: float,
        limit: int,
        bbox: Optional[List[float]] = None,
    ) -> List["Location"]:
        """
        Dynamically enumerate populated sub-areas (suburb / neighborhood /
        district / town) covering a city, worldwide. Multi-anchor coverage +
        geographic scope enforcement (bbox containment, else radius). Geoapify
        Places primary; Nominatim viewbox fallback. No corpus, no boundary
        datasets.
        """
        return await self._gather_places(
            lat, lon, radius_m=radius_m, limit=limit,
            categories="populated_place", bbox=bbox,
        )

    @ttl_cache(ttl=43200)
    async def explore(
        self,
        lat: float,
        lon: float,
        *,
        radius_m: float,
        limit: int,
        categories: str,
        bbox: Optional[List[float]] = None,
    ) -> List["Location"]:
        """
        Dynamic city exploration: discover places of arbitrary Geoapify
        categories around a city, worldwide. Same multi-anchor coverage +
        scope enforcement as nearby_areas. Geoapify Places primary; Nominatim
        viewbox fallback. No corpus, no scoring — pure discovery.
        """
        return await self._gather_places(
            lat, lon, radius_m=radius_m, limit=limit,
            categories=categories, bbox=bbox,
        )

    async def _gather_places(
        self,
        lat: float,
        lon: float,
        *,
        radius_m: float,
        limit: int,
        categories: str,
        bbox: Optional[List[float]],
    ) -> List["Location"]:
        radius = max(1000.0, min(radius_m or 0.0, 50_000.0))
        anchors = _anchor_points(lat, lon, bbox)
        # Each anchor sweeps a smaller circle; the union covers the whole city.
        anchor_radius = radius if len(anchors) == 1 else max(3000.0, radius / 2.0)

        collected: List["Location"] = []
        for alat, alon in anchors:
            collected.extend(
                await self._geoapify_places(
                    alat, alon, radius=anchor_radius, limit=limit, categories=categories
                )
            )

        if not collected:
            # Fallback path: single Nominatim viewbox sweep (areas only).
            collected = await self._nominatim_areas(lat, lon, radius=radius, limit=limit)

        in_scope = [
            loc
            for loc in collected
            if self._in_scope(loc, lat, lon, bbox, radius)
        ]
        return _dedup_locations(in_scope)

    @staticmethod
    def _in_scope(
        loc: "Location",
        center_lat: float,
        center_lon: float,
        bbox: Optional[List[float]],
        radius: float,
    ) -> bool:
        """Geographic scope enforcement — eliminates cross-city leakage.

        Preferred: bbox containment (the city's administrative bounds).
        Fallback: adaptive radius from the center when no bbox is available.
        """
        if bbox and len(bbox) == 4:
            return _point_in_bbox(loc.lat, loc.lon, bbox, pad=0.01)
        return _haversine_m(center_lat, center_lon, loc.lat, loc.lon) <= radius

    # ── Geoapify ───────────────────────────────────────────────────────────────
    async def _geoapify_forward(
        self, text: str, *, limit: int, autocomplete: bool, bias: Optional[tuple] = None
    ) -> List["Location"]:
        key = settings.GEOAPIFY_API_KEY
        if not key:
            return []
        endpoint = "autocomplete" if autocomplete else "search"
        url = (
            f"https://api.geoapify.com/v1/geocode/{endpoint}"
            f"?text={quote(text, safe='')}&limit={limit}&apiKey={key}"
        )
        if bias is not None:
            url += f"&bias=proximity:{bias[1]},{bias[0]}"
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("geocode.geoapify.bad_status", status=resp.status)
                        return []
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001 — soft failure, fall back
            logger.warning("geocode.geoapify.error", error=str(exc))
            return []

        out: List["Location"] = []
        for feat in (data.get("features") or []):
            loc = self._from_geoapify(feat)
            if loc:
                out.append(loc)
        return out

    async def _geoapify_reverse(self, lat: float, lon: float) -> Optional["Location"]:
        key = settings.GEOAPIFY_API_KEY
        if not key:
            return None
        url = (
            f"https://api.geoapify.com/v1/geocode/reverse"
            f"?lat={lat}&lon={lon}&limit=1&apiKey={key}"
        )
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("geocode.geoapify.reverse_error", error=str(exc))
            return None
        feats = data.get("features") or []
        return self._from_geoapify(feats[0]) if feats else None

    def _from_geoapify(self, feat: Dict[str, Any]) -> Optional["Location"]:
        from apps.api.models.location import Location

        props = (feat or {}).get("properties") or {}
        lat = _coerce_float(props.get("lat"))
        lon = _coerce_float(props.get("lon"))
        if lat is None or lon is None:
            return None

        rtype = str(props.get("result_type") or "").lower()
        ctype = _GEOAPIFY_TYPE_MAP.get(rtype, rtype if rtype in _canon() else "place")
        rank = props.get("rank") or {}
        place_id = props.get("place_id") or f"{lat},{lon}"
        bbox = props.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            box = [
                _coerce_float(bbox[0]),
                _coerce_float(bbox[1]),
                _coerce_float(bbox[2]),
                _coerce_float(bbox[3]),
            ]
            box = box if all(v is not None for v in box) else None
        else:
            box = None

        # Addresses and streets have no `name`; fall back to the street line
        # ("12 Westland Avenue"), not the city — otherwise every address in
        # a city shows up as "Boston" and nearby ones dedupe into one.
        if ctype in ("address", "street"):
            street_line = props.get("address_line1") or " ".join(
                str(p) for p in (props.get("housenumber"), props.get("street")) if p
            )
            display_name = props.get("name") or street_line or props.get("formatted")
        else:
            display_name = props.get("name") or props.get("city") or props.get("formatted")

        return Location(
            id=f"geoapify:{place_id}",
            type=ctype,
            name=str(display_name or "").strip() or str(props.get("formatted") or "Unknown"),
            label=str(props.get("formatted") or props.get("name") or "Unknown"),
            lat=lat,
            lon=lon,
            bbox=box,
            country=props.get("country"),
            country_code=(str(props.get("country_code")).upper() if props.get("country_code") else None),
            region=props.get("state"),
            city=props.get("city"),
            district=props.get("district"),
            suburb=props.get("suburb"),
            postcode=props.get("postcode"),
            provider="geoapify",
            confidence=_coerce_float(rank.get("confidence")) or 0.0,
            state=props.get("state"),
            short_description=props.get("address_line2") or None,
            population=_geoapify_population(props),
            raw=props,
        )

    async def _geoapify_places(
        self,
        lat: float,
        lon: float,
        *,
        radius: float,
        limit: int,
        categories: str = "populated_place",
    ) -> List["Location"]:
        key = settings.GEOAPIFY_API_KEY
        if not key:
            return []
        url = (
            "https://api.geoapify.com/v2/places"
            f"?categories={quote(categories, safe=',')}"
            f"&filter=circle:{lon},{lat},{int(radius)}"
            f"&bias=proximity:{lon},{lat}"
            f"&limit={max(1, min(limit, 100))}&apiKey={key}"
        )
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning("geocode.geoapify.places_bad_status", status=resp.status)
                        return []
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("geocode.geoapify.places_error", error=str(exc))
            return []

        out: List["Location"] = []
        seen: set = set()
        for feat in (data.get("features") or []):
            loc = self._from_geoapify_place(feat, radius=radius)
            if loc and loc.id not in seen:
                seen.add(loc.id)
                out.append(loc)
        return out

    def _from_geoapify_place(
        self, feat: Dict[str, Any], *, radius: float
    ) -> Optional["Location"]:
        from apps.api.models.location import Location

        props = (feat or {}).get("properties") or {}
        lat = _coerce_float(props.get("lat"))
        lon = _coerce_float(props.get("lon"))
        name = str(props.get("name") or "").strip()
        if lat is None or lon is None or not name:
            return None

        cats = [str(c).lower() for c in (props.get("categories") or [])]
        joined = " ".join(cats)
        ctype: Optional[str] = None
        for needle, mapped in _PLACE_SUBTYPE_MAP:
            if needle in joined:
                ctype = mapped
                break
        if ctype is None:
            if "populated_place" in joined:
                # populated_place without a recognized subtype → area-level.
                ctype = "suburb"
            elif any(
                k in joined
                for k in ("tourism", "leisure", "entertainment", "heritage", "natural")
            ):
                # named point feature (park, sight, attraction, ...) → landmark.
                ctype = "landmark"
            else:
                # genuinely unclassified feature → generic "place".
                ctype = "place"

        distance = _coerce_float(props.get("distance"))
        if distance is not None and radius > 0:
            confidence = round(max(0.0, min(1.0, 1.0 - distance / radius)), 3)
        else:
            confidence = 0.5

        place_id = props.get("place_id") or f"{lat},{lon}"
        state = props.get("state")
        return Location(
            id=f"geoapify:{place_id}",
            type=ctype,
            name=name,
            label=str(props.get("formatted") or name),
            lat=lat,
            lon=lon,
            bbox=None,
            country=props.get("country"),
            country_code=(str(props.get("country_code")).upper() if props.get("country_code") else None),
            region=state,
            city=props.get("city"),
            district=props.get("district"),
            suburb=props.get("suburb"),
            postcode=props.get("postcode"),
            provider="geoapify",
            confidence=confidence,
            state=state,
            short_description=props.get("address_line2") or None,
            population=_geoapify_population(props),
            tags=_geoapify_place_tags(props),
            raw=props,
        )

    # ── Nominatim ──────────────────────────────────────────────────────────────
    async def _nominatim_areas(
        self, lat: float, lon: float, *, radius: float, limit: int
    ) -> List["Location"]:
        # Bounded free-text fallback: query OSM place nodes inside a viewbox
        # around the center. Coarser than Geoapify Places, but global + dynamic.
        deg = max(0.02, radius / 111_000.0)
        left, right = lon - deg, lon + deg
        top, bottom = lat + deg, lat - deg
        url = (
            f"{settings.NOMINATIM_URL}/search"
            f"?q=neighbourhood&format=jsonv2&addressdetails=1&limit={max(1, min(limit, 40))}"
            f"&viewbox={left},{top},{right},{bottom}&bounded=1"
        )
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url, headers=_NOMINATIM_HEADERS) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("geocode.nominatim.areas_error", error=str(exc))
            return []
        out: List["Location"] = []
        seen: set = set()
        for item in (data or []):
            loc = self._from_nominatim(item)
            if loc and loc.type in ("suburb", "neighborhood", "district", "city") and loc.id not in seen:
                seen.add(loc.id)
                out.append(loc)
        return out


    async def _photon_forward(self, text: str, *, limit: int, bias: Optional[tuple]) -> List["Location"]:
        """Photon, location-biased: the city's own areas and places first."""
        params: Dict[str, Any] = {"q": text, "limit": str(min(limit, 15)), "lang": "en"}
        if bias is not None:
            params.update({"lat": str(bias[0]), "lon": str(bias[1]), "location_bias_scale": "0.3"})
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(f"{settings.PHOTON_URL}/api/", params=params, headers=_PHOTON_HEADERS) as resp:
                    if resp.status != 200:
                        logger.info("geocode.photon.bad_status", status=resp.status)
                        return []
                    data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            logger.info("geocode.photon.error", error=type(exc).__name__)
            return []
        out: List["Location"] = []
        for i, feature in enumerate((data or {}).get("features") or []):
            loc = _from_photon(feature, i)
            if loc:
                out.append(loc)
        return out

    async def _nominatim_forward(
        self, text: str, *, limit: int, bias: Optional[tuple] = None
    ) -> List["Location"]:
        url = (
            f"{settings.NOMINATIM_URL}/search"
            f"?q={quote(text, safe='')}&format=jsonv2"
            f"&addressdetails=1&namedetails=1&limit={limit}"
        )
        if bias is not None:
            # Prefer (not restrict to) a ~60 km box around the user's city.
            lat, lon = bias
            url += f"&viewbox={lon - 0.6},{lat + 0.45},{lon + 0.6},{lat - 0.45}&bounded=0"
        try:
            await _nominatim_throttle()
        except _NominatimBusy:
            return []
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url, headers=_NOMINATIM_HEADERS) as resp:
                    if resp.status != 200:
                        logger.warning("geocode.nominatim.bad_status", status=resp.status)
                        return []
                    data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("geocode.nominatim.error", error=str(exc))
            return []
        out: List["Location"] = []
        for item in (data or []):
            loc = self._from_nominatim(item)
            if loc:
                out.append(loc)
        return out

    async def _nominatim_reverse(self, lat: float, lon: float) -> Optional["Location"]:
        url = (
            f"{settings.NOMINATIM_URL}/reverse"
            f"?lat={lat}&lon={lon}&format=jsonv2&addressdetails=1"
        )
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.get(url, headers=_NOMINATIM_HEADERS) as resp:
                    if resp.status != 200:
                        return None
                    item = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("geocode.nominatim.reverse_error", error=str(exc))
            return None
        if not item or "lat" not in item:
            return None
        return self._from_nominatim(item)

    def _from_nominatim(self, item: Dict[str, Any]) -> Optional["Location"]:
        from apps.api.models.location import Location

        lat = _coerce_float(item.get("lat"))
        lon = _coerce_float(item.get("lon"))
        if lat is None or lon is None:
            return None

        addr = item.get("address") or {}
        addresstype = str(item.get("addresstype") or item.get("type") or "").lower()
        ctype = _NOMINATIM_TYPE_MAP.get(addresstype, "place")

        bb = item.get("boundingbox")  # [south, north, west, east] as strings
        box = None
        if isinstance(bb, list) and len(bb) == 4:
            south, north, west, east = (_coerce_float(v) for v in bb)
            if None not in (south, north, west, east):
                box = [west, south, east, north]

        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
        display = item.get("display_name") or item.get("name") or "Unknown"
        short = (
            item.get("name")
            or addr.get(addresstype)
            or city
            or str(display).split(",")[0]
        )
        osm_id = item.get("osm_id") or item.get("place_id") or f"{lat},{lon}"

        return Location(
            id=f"nominatim:{osm_id}",
            type=ctype,
            name=str(short).strip() or "Unknown",
            label=str(display),
            lat=lat,
            lon=lon,
            bbox=box,
            country=addr.get("country"),
            country_code=(str(addr.get("country_code")).upper() if addr.get("country_code") else None),
            region=addr.get("state") or addr.get("region"),
            city=city,
            district=addr.get("city_district") or addr.get("district"),
            suburb=addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter"),
            postcode=addr.get("postcode"),
            provider="nominatim",
            confidence=_coerce_float(item.get("importance")) or 0.0,
            state=addr.get("state") or addr.get("region"),
            short_description=(
                str(display).split(",", 1)[1].strip()
                if isinstance(display, str) and "," in display
                else None
            ),
            population=_coerce_int((item.get("extratags") or {}).get("population")),
            tags=[t for t in {ctype, item.get("category"), addresstype} if isinstance(t, str) and t and t != "unknown"],
            raw=item,
        )


_ACRONYM_GEOAPIFY_TIMEOUT_S = 2.5
_PHOTON_TIMEOUT_S = 2.5
_PHOTON_HEADERS = {"User-Agent": "Navis/1.0 (city companion; geocoding)"}

# Photon `osm_key=place` values → Location types.
_PHOTON_PLACE = {
    "suburb": "suburb", "quarter": "suburb", "borough": "suburb", "city_district": "district",
    "neighbourhood": "neighborhood", "locality": "neighborhood", "isolated_dwelling": "neighborhood",
    "city": "city", "town": "city", "village": "city", "hamlet": "city", "municipality": "city",
    "county": "county", "state": "region", "region": "region", "province": "region", "country": "country",
}
_PHOTON_ADMIN = {"city": "city", "district": "district", "county": "county", "state": "region", "country": "country"}


def _photon_type(p: Dict[str, Any]) -> str:
    key, value, kind = p.get("osm_key"), p.get("osm_value"), p.get("type")
    if key == "place":
        # Islands, archipelagos and the like: a place, not a neighbourhood.
        return _PHOTON_PLACE.get(str(value), "landmark")
    if key == "boundary":
        return _PHOTON_ADMIN.get(str(kind), "district")
    if p.get("housenumber"):
        return "address"
    if key == "highway":
        return "street"
    if value == "postcode" or kind == "postcode":
        return "postcode"
    return "landmark"


def _from_photon(feature: Dict[str, Any], rank: int) -> Optional["Location"]:
    from apps.api.models.location import Location

    p = feature.get("properties") or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) != 2 or not p.get("name") and not p.get("street"):
        return None
    lon, lat = _coerce_float(coords[0]), _coerce_float(coords[1])
    if lat is None or lon is None:
        return None
    ctype = _photon_type(p)
    name = str(p.get("name") or f"{p.get('housenumber', '')} {p.get('street', '')}".strip())
    city = p.get("city") or (p.get("name") if ctype == "city" else None)
    parts: List[str] = []
    for part in (name, p.get("locality"), p.get("district"), city, p.get("county") if not city else None,
                 " ".join(x for x in (p.get("state"), p.get("postcode")) if x) or None, p.get("country")):
        if part and part not in parts:
            parts.append(str(part))
    ext = p.get("extent")  # [minLon, maxLat, maxLon, minLat]
    box = [ext[0], ext[3], ext[2], ext[1]] if isinstance(ext, list) and len(ext) == 4 else None
    return Location(
        id=f"photon:{p.get('osm_type', '')}{p.get('osm_id', f'{lat},{lon}')}",
        type=ctype,
        name=name,
        label=", ".join(parts),
        lat=lat,
        lon=lon,
        bbox=box,
        country=p.get("country"),
        country_code=(str(p["countrycode"]).upper() if p.get("countrycode") else None),
        region=p.get("state"),
        city=city,
        district=p.get("district"),
        suburb=p.get("locality") if ctype not in ("suburb", "neighborhood") else name,
        postcode=p.get("postcode"),
        provider="photon",
        # Photon returns results best-first without a score.
        confidence=max(0.4, 0.85 - 0.04 * rank),
        state=p.get("state"),
        short_description=", ".join(parts[1:]) or None,
        tags=[t for t in {ctype, p.get("osm_key"), p.get("osm_value")} if isinstance(t, str) and t],
        raw={"osm_key": p.get("osm_key"), "osm_value": p.get("osm_value")},
    )


async def _with_timeout(coro, timeout_s: float) -> List["Location"]:
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except asyncio.TimeoutError:
        return []


_ALIAS_KEYS = ("short_name", "alt_name", "nickname", "official_name", "old_name",
               "loc_name", "name:en", "short_name:en", "alt_name:en")


def _alias_names(loc: "Location") -> set:
    """Normalized OSM aliases of a Nominatim result (empty for others)."""
    raw = loc.raw if isinstance(getattr(loc, "raw", None), dict) else {}
    details = raw.get("namedetails") or {}
    out = set()
    for k in _ALIAS_KEYS:
        v = details.get(k)
        if isinstance(v, str):
            for part in v.split(";"):  # OSM separates multiple values with ';'
                n = _norm_name(part)
                if n:
                    out.add(n)
    return out


# Nominatim's usage policy allows ~1 request/second; core/throttle.py
# spaces calls across the deployment. Autocomplete skips instead of
# queueing: during fast typing the queued calls would be stale.
from apps.api.core.throttle import NominatimBusy as _NominatimBusy  # noqa: E402
from apps.api.core.throttle import nominatim_slot  # noqa: E402


async def _nominatim_throttle() -> None:
    await nominatim_slot(skip_if_busy=True)


def _canon() -> set:
    from apps.api.models.location import LOCATION_TYPES

    return set(LOCATION_TYPES)


# Module-level singleton; routes + nodes import this.
geocoding_service = GeocodingService()
