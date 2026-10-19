"""
ContextRetrievalNode — pulls relevant knowledge chunks for a query.

Config:

  type: context_retrieval
  config:
    workflow: explore_city            # static facet filters
    tags: [cafes, metro]
    city: ${ctx.user.city}            # resolver-aware
    limit: 5
    generate_local: true              # optional, see below
    place: ${ctx.user.cityLocation}   # optional Location (country, region)

Returns a dict: {chunks: [..]} where each chunk is a serialisable view.
Downstream nodes (humanization especially) can incorporate the chunks as
soft context; nothing forces them to.

Failure is soft: if the corpus is empty or no chunks match, the node
returns an empty list rather than failing the workflow.

`generate_local`: when the requested city has no hand-written chunks, add
place-specific items from services/place_guide.py (LLM-generated, cached
per place) ahead of the universal ones. Hand-written cities are unchanged.
"""
from __future__ import annotations

from typing import Any

from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.context_retriever import context_retriever
from apps.api.services.place_guide import guide_for


@register("context_retrieval")
class ContextRetrievalNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config

        city = resolve(cfg.get("city"), ctx) if cfg.get("city") else None
        workflow = resolve(cfg.get("workflow"), ctx) if cfg.get("workflow") else None
        tags_raw = resolve(cfg.get("tags"), ctx) if cfg.get("tags") else None
        if isinstance(tags_raw, str):
            tags_raw = [tags_raw]

        limit = int(cfg.get("limit", 5))

        chunks = context_retriever.retrieve(
            ctx.query,
            city=city,
            workflow=workflow,
            tags=tags_raw,
            limit=limit,
        )
        views = [c.to_view() for c in chunks]

        if cfg.get("generate_local") and isinstance(city, str) and city.strip():
            city_l = city.strip().lower()
            if not any(c.city == city_l for c in chunks):
                place = resolve(cfg.get("place"), ctx) if cfg.get("place") else None
                place = place if isinstance(place, dict) else {}
                generated = await guide_for(
                    city.strip(),
                    country_code=place.get("country_code"),
                    country=place.get("country"),
                    region=place.get("region") or place.get("state"),
                    exclude_titles=[v["frontmatter"].get("title", "") for v in views],
                )
                views = generated + views
                limit = max(limit, len(views))

        return {"chunks": views[:limit]}
