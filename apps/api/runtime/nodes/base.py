"""
Node base class.

A Node is a stateless execution unit. The runtime instantiates one per
execution from `spec`, calls `await node.execute(ctx)`, and discards it.
Nodes never hold per-run state — that's what NodeContext + Blackboard
are for.

Lifecycle (per call):
  1. Scheduler resolves the spec.type via NodeRegistry to a Node subclass.
  2. Scheduler constructs the node with its NodeSpec.
  3. Scheduler builds a NodeContext (spec + execution + resolved inputs).
  4. Scheduler awaits node.execute(ctx). The return value is published to
     the blackboard under spec.output_key.
  5. Any raised exception is caught by the scheduler, retried per spec,
     and ultimately reported via NODE_FAILED.

Optional declarations (subclass class attributes):
  * `contract: NodeContract | None` — compile-time validation of config
    shape + execution semantics. None = no validation.
  * `canonicalize_dedup_key(spec) -> bytes | None` — semantic equivalence
    hook used by DedupPass. Returning None opts out of dedup. Default
    implementation is structural (orjson sort-keys of (type, config)).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional

import orjson

from apps.api.runtime.context import NodeContext
from apps.api.runtime.contracts import NodeContract
from apps.api.runtime.graph import NodeSpec


class Node(ABC):
    type_name: str = ""               # set by @register; used only for debugging
    contract: ClassVar[Optional[NodeContract]] = None

    def __init__(self, spec: NodeSpec) -> None:
        self.spec = spec

    @abstractmethod
    async def execute(self, ctx: NodeContext) -> Any:
        """Run the node. Return value becomes the blackboard output."""

    @classmethod
    def canonicalize_dedup_key(cls, spec: NodeSpec) -> Optional[bytes]:
        """
        Return a canonical byte string that identifies this node as
        equivalent to another for dedup purposes. Two nodes that produce
        the same key are considered identical executions and will be
        collapsed by DedupPass.

        Returning None opts out — the node will never be deduped against
        any other.

        Default: structural equality on (type, config) via orjson with
        sorted keys. Subclasses override for semantic equivalence (e.g.
        normalize whitespace + case on string args).
        """
        return orjson.dumps(
            (cls.type_name or cls.__name__, spec.config),
            option=orjson.OPT_SORT_KEYS,
        )


def register(type_name: str):
    """Decorator: register a Node subclass against the global registry."""
    from apps.api.runtime.registry import node_registry

    def _wrap(cls):
        cls.type_name = type_name
        node_registry.register(type_name, cls)
        return cls

    return _wrap
