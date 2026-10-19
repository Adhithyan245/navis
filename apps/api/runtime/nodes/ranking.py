"""
RankingNode — sorts items via RankingService.

Config:

  type: ranking
  config:
    kind: places       # places | events | services
    source: ${fuse.data}   # items to rank (defaults to upstream fusion output)
    anchor: ${ctx.user.home_anchor}  # optional anchor location for distance scoring
    limit: 20          # optional cap on returned items
"""
from __future__ import annotations

from typing import Any, Dict, List

from apps.api.models.context import UserContext
from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.ranking import ranking_service


def _to_user_context(raw: Dict[str, Any]) -> UserContext:
    """Build a UserContext from a plain dict, tolerating missing fields."""
    if not raw:
        return UserContext()
    try:
        return UserContext.model_validate(raw)
    except Exception:
        # Construct an empty context and copy whatever fields fit
        ctx = UserContext()
        for key in (
            "preferences", "food_preferences", "dislikes", "event_categories",
            "budget", "home_anchor", "work_anchor",
        ):
            if key in raw:
                try:
                    setattr(ctx, key, raw[key])
                except Exception:
                    pass
        return ctx


@register("ranking")
class RankingNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config
        kind = cfg.get("kind", "places")

        # Resolve the items to rank. If no source is given, take the first
        # upstream dep that produced a list-shaped output.
        if "source" in cfg:
            items = resolve(cfg["source"], ctx)
        else:
            items = None
            for dep_id, result in ctx.inputs.items():
                if not result.ok or result.output is None:
                    continue
                out = result.output
                if isinstance(out, dict) and isinstance(out.get("data"), list):
                    items = out["data"]
                    break
                if isinstance(out, list):
                    items = out
                    break

        items = items or []
        if not isinstance(items, list):
            items = list(items) if hasattr(items, "__iter__") else []

        anchor = resolve(cfg.get("anchor"), ctx) if cfg.get("anchor") else None
        user_ctx = _to_user_context(ctx.user_context)

        if kind == "places":
            ranked: List[Dict[str, Any]] = ranking_service.rank_places(
                items, user_ctx, anchor_location=anchor,
            )
        elif kind == "events":
            ranked = ranking_service.rank_events(items, user_ctx)
        elif kind == "services":
            ranked = ranking_service.rank_services(items, anchor_location=anchor)
        else:
            raise ValueError(f"RankingNode {self.spec.id!r}: unknown kind {kind!r}")

        limit = cfg.get("limit")
        if isinstance(limit, int) and limit > 0:
            ranked = ranked[:limit]

        return ranking_service.strip_ranking_metadata(ranked)
