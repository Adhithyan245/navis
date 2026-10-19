"""
StreamingNode — emits a FINAL_RESULT event with the assembled payload.

Config:

  type: stream
  config:
    payload:                              # arbitrary, resolver-aware
      results: ${rank.}                   # whole upstream output
      providers_used: ${fuse.providers_used}
      query: ${ctx.query}

The node returns the same payload as its blackboard output so downstream
nodes (if any) can still consume it. Most workflows terminate here.
"""
from __future__ import annotations

from typing import Any

from apps.api.runtime.context import NodeContext
from apps.api.runtime.events import EventType
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.resolver import resolve


@register("stream")
class StreamingNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config
        raw_payload = cfg.get("payload", {})
        payload = resolve(raw_payload, ctx)
        event_type = EventType.FINAL_RESULT
        if cfg.get("partial", False):
            event_type = EventType.PARTIAL_RESULT
        await ctx.events.emit(event_type, payload)
        return payload
