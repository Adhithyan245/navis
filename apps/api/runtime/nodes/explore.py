"""
CityExploreNode — dynamic, worldwide city exploration. Backs the
`city_explorer` workflow. Discovers places of various kinds (neighborhoods,
districts, landmarks, parks, shopping/business areas, transit hubs) around a
resolved city center, using the geocoding/places provider layer only — no
corpus, no scoring, no ranking.

Config:

  type: city_explore
  config:
    location: ${ctx.user.cityLocation}   # resolved Location dict (preferred)
    city: ${ctx.user.city}               # text fallback
    category: ${ctx.user.category}       # optional facet (see CATEGORY_MAP)
    limit: 30

Returns: {"city": <center Location dict | None>, "category": <str|None>,
          "results": [Location dict, ...]}

Each result is a canonical Location. Failure is soft (empty results).
"""
from __future__ import annotations

from typing import Any, Optional

from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.geo_common import center_radius_m, resolve_center
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.geocoding import geocoding_service

# User-facing facet → Geoapify Places categories. Unknown / absent facet uses
# DEFAULT (a broad mix across every discovery type). Facets are geography-
# agnostic — they map to OSM/Geoapify category taxonomy, never to a place.
CATEGORY_MAP = {
    "neighborhoods": "populated_place",
    "districts": "populated_place",
    "suburbs": "populated_place",
    "landmarks": "tourism.sights,tourism.attraction",
    "points_of_interest": "tourism,entertainment",
    "cafes": "catering.cafe",
    "restaurants": "catering.restaurant",
    "food": "catering.cafe,catering.restaurant",
    "parks": "leisure.park,national_park",
    "shopping": "commercial.shopping_mall,commercial.marketplace",
    "business": "commercial,office",
    "healthcare": "healthcare",
    "gyms": "sport.fitness,leisure.fitness_centre",
    "fitness": "sport.fitness,leisure.fitness_centre",
    "transit": "public_transport,airport",
}

# Broad multi-category default so a no-facet "explore" sweep covers the full
# POI spectrum (areas + cafes + restaurants + parks + transit + healthcare +
# gyms + shopping) uniformly across anchors.
DEFAULT_CATEGORIES = ",".join(
    [
        "populated_place",
        "tourism.sights",
        "catering.cafe",
        "catering.restaurant",
        "leisure.park",
        "commercial.shopping_mall",
        "public_transport",
        "healthcare",
        "sport.fitness",
    ]
)


@register("city_explore")
class CityExploreNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config
        limit = int(cfg.get("limit", 30))

        category = self._resolve_category(cfg, ctx)
        categories = CATEGORY_MAP.get(category or "", DEFAULT_CATEGORIES)

        center = await resolve_center(cfg, ctx)
        if center is None:
            return {"city": None, "category": category, "results": []}

        results = await geocoding_service.explore(
            float(center["lat"]),
            float(center["lon"]),
            radius_m=center_radius_m(center),
            limit=limit,
            categories=categories,
            bbox=center.get("bbox"),
        )
        return {
            "city": center,
            "category": category,
            "results": [r.model_dump() for r in results],
        }

    def _resolve_category(self, cfg: dict, ctx: NodeContext) -> Optional[str]:
        raw = resolve(cfg.get("category"), ctx) if cfg.get("category") else None
        if isinstance(raw, (list, tuple)):
            raw = next((str(t) for t in raw if t), "")
        value = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
        return value or None
