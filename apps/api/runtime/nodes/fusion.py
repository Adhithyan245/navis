"""
FusionNode — merges upstream ProviderResponse objects into a unified list.

Config:

  type: fusion
  config:
    inputs: [places_search, events_search, wiki_search]   # node ids
    # OR omit `inputs` to fuse every successful dependency

Returns the dict produced by FusionEngine.merge(): {total_results, data,
providers_used, fallback_used}. Downstream nodes typically pull `.data`.
"""
from __future__ import annotations

from typing import Any, List

from apps.api.models.providers import ProviderResponse
from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.services.fusion import fusion_engine


@register("fusion")
class FusionNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config
        explicit_inputs = cfg.get("inputs")

        sources: List[ProviderResponse] = []
        for dep_id, result in ctx.inputs.items():
            if explicit_inputs is not None and dep_id not in explicit_inputs:
                continue
            if not result.ok or result.output is None:
                continue
            if isinstance(result.output, ProviderResponse):
                sources.append(result.output)

        return fusion_engine.merge(sources)
