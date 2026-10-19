"""
ProviderNode — calls a provider through the existing ProviderManager.

Config shape (in workflow YAML):

  type: provider
  config:
    provider: geo        # one of: geo, places, transit, events, wiki, ai
    method: execute      # provider method name; defaults to "execute"
    args:                # kwargs for the provider method (resolver-aware)
      query: ${ctx.query}
      lat: ${geo_search.results.0.lat}
      lon: ${geo_search.results.0.lng}

The node returns the full ProviderResponse object. Downstream nodes can
reach into `${this_node.results}` to grab the result list directly.

A `PROVIDER_FALLBACK` event is emitted when the response's `source` is
`"fallback"`, so observers can react to degraded providers without
inspecting the payload.
"""
from __future__ import annotations

from typing import Any, Optional

import orjson

from apps.api.runtime.context import NodeContext
from apps.api.runtime.contracts import ConfigField, NodeContract
from apps.api.runtime.events import EventType
from apps.api.runtime.graph import NodeSpec
from apps.api.runtime.nodes.base import Node, register
from apps.api.runtime.nodes.resolver import resolve
from apps.api.services.provider_manager import provider_manager


_PROVIDER_ATTRS = {
    "geo": "geo",
    "places": "places",
    "transit": "transit",
    "events": "events",
    "wiki": "wiki",
    "ai": "ai",
}


def _canonicalize_arg_value(v: Any) -> Any:
    """Normalize a single argument value for dedup-key purposes.

    Resolver-string args (`${...}`) are passed through untouched — they're
    already identical between equivalent calls. Literal strings get
    whitespace + case normalized so 'Chennai' and ' chennai ' collapse.
    Other types pass through unchanged.
    """
    if isinstance(v, str):
        if v.startswith("${"):
            return v
        return " ".join(v.lower().strip().split())
    if isinstance(v, dict):
        return {k: _canonicalize_arg_value(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_canonicalize_arg_value(x) for x in v]
    return v


@register("provider")
class ProviderNode(Node):
    contract = NodeContract(
        name="provider",
        config_fields=(
            ConfigField("provider", required=True,
                        description="One of: geo, places, transit, events, wiki, ai"),
            ConfigField("args", required=False,
                        description="kwargs passed to the provider method"),
            ConfigField("method", required=False,
                        description="Method to call; defaults to 'execute'"),
            ConfigField("drop_none_args", required=False),
        ),
        emits_kind="provider_response",
        cancellation_safe=True,
        retry_safe=True,
    )

    @classmethod
    def canonicalize_dedup_key(cls, spec: NodeSpec) -> Optional[bytes]:
        """Two provider nodes are equivalent if they target the same
        provider+method and would send equivalent arguments after
        normalization. This catches the 'Chennai' vs ' Chennai ' case
        the spec called out without trying to invent NLP-level
        equivalence (which would belong inside the geo provider, not
        here)."""
        cfg = spec.config
        canonical_args = _canonicalize_arg_value(cfg.get("args", {}) or {})
        key = (
            cls.type_name or cls.__name__,
            cfg.get("provider"),
            cfg.get("method", "execute"),
            canonical_args,
        )
        return orjson.dumps(key, option=orjson.OPT_SORT_KEYS)

    async def execute(self, ctx: NodeContext) -> Any:
        cfg = self.spec.config
        provider_key = cfg.get("provider")
        if provider_key not in _PROVIDER_ATTRS:
            raise ValueError(
                f"ProviderNode {self.spec.id!r}: unknown provider {provider_key!r}. "
                f"Known: {sorted(_PROVIDER_ATTRS)}"
            )

        provider = getattr(provider_manager, _PROVIDER_ATTRS[provider_key])
        method_name = cfg.get("method", "execute")
        method = getattr(provider, method_name, None)
        if method is None or not callable(method):
            raise ValueError(
                f"ProviderNode {self.spec.id!r}: provider {provider_key!r} has no method {method_name!r}"
            )

        raw_args = cfg.get("args", {}) or {}
        kwargs = resolve(raw_args, ctx)
        if not isinstance(kwargs, dict):
            raise ValueError(
                f"ProviderNode {self.spec.id!r}: resolved args must be a dict, got {type(kwargs).__name__}"
            )

        # Strip any keys whose resolution came back None unless the workflow
        # explicitly opted into nullable args. Most provider methods reject
        # None kwargs, and silently dropping them yields better fallback
        # behaviour than crashing.
        if cfg.get("drop_none_args", True):
            kwargs = {k: v for k, v in kwargs.items() if v is not None}

        response = await method(**kwargs)

        if getattr(response, "source", None) == "fallback":
            await ctx.events.emit(
                EventType.PROVIDER_FALLBACK,
                {
                    "node_id": self.spec.id,
                    "provider": provider_key,
                    "error": getattr(response, "error", None),
                },
            )

        return response
