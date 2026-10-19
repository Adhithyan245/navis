"""
GeocodeNode — resolves text / coordinates to canonical Location(s).

Config:

  type: geocode
  config:
    text: ${ctx.user.city}     # resolver-aware; defaults to ctx.query
    limit: 1                    # how many candidates to return
    autocomplete: false

Returns: {"location": <top Location dict | None>, "locations": [Location dict, ...]}

Failure is soft: provider errors yield an empty result rather than failing
the workflow (mirrors ContextRetrievalNode's contract).
"""
from __future__ import annotations

from typing import Any

from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.geocoding import geocoding_service


@register("geocode")
class GeocodeNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config

        text = resolve(cfg.get("text"), ctx) if cfg.get("text") else ctx.query
        if isinstance(text, (list, tuple)):
            text = next((str(t) for t in text if t), "")
        text = str(text or "").strip()

        limit = int(cfg.get("limit", 1))
        autocomplete = bool(cfg.get("autocomplete", False))

        if not text:
            return {"location": None, "locations": []}

        locations = await geocoding_service.search(
            text, limit=limit, autocomplete=autocomplete
        )
        views = [loc.model_dump() for loc in locations]
        return {"location": views[0] if views else None, "locations": views}
