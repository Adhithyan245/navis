"""
HumanizationNode — turns structured results into conversational prose.

Wraps the existing HumanizationService. The service itself is fail-soft:
it never raises and falls back to deterministic templating if the LLM
provider is degraded, so the node simply forwards whatever string comes
back.

Config:

  type: humanization
  config:
    source: ${rank_results}     # data passed into format_response
    context_keys: [city, preferences]   # optional: subset of user_context to pass
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from apps.api.runtime.context import NodeContext
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.humanization import humanization_service


def _build_data_blob(value: Any) -> Dict[str, Any]:
    """Coerce node output (list / dict / None) into the dict shape humanization expects."""
    if value is None:
        return {"results": []}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"results": value}
    return {"results": [value]}


def _filter_context(user_context: Dict[str, Any], keys: Optional[list]) -> Dict[str, Any]:
    if not keys:
        return dict(user_context) if isinstance(user_context, dict) else {}
    return {k: user_context[k] for k in keys if k in user_context}


@register("humanization")
class HumanizationNode(Node):
    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config

        if "source" in cfg:
            raw = resolve(cfg["source"], ctx)
        else:
            # Pick the first successful upstream dep whose output is list/dict shaped.
            raw = None
            for dep_id, result in ctx.inputs.items():
                if not result.ok or result.output is None:
                    continue
                if isinstance(result.output, (dict, list)):
                    raw = result.output
                    break

        data = _build_data_blob(raw)
        keys = cfg.get("context_keys")
        scoped_ctx = _filter_context(ctx.user_context, keys)

        text = await humanization_service.format_response(ctx.query, scoped_ctx, data)
        return {
            "text": text,
            "result_count": len(data.get("results", [])) if isinstance(data.get("results"), list) else 0,
        }
