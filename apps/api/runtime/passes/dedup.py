"""
DedupPass — collapse equivalent root nodes into one execution.

"Equivalent" is delegated to each Node subclass's `canonicalize_dedup_key`
classmethod, which returns a `bytes` value. Nodes with the same key are
considered the same execution; ProviderNode normalizes string args
(whitespace + case) so 'Chennai' and ' Chennai ' collapse. Returning
None opts a node out of dedup entirely.

Why only roots? Non-root nodes carry resolver refs to upstream outputs.
Two nodes that read `${A}` and `${B}` aren't equivalent unless A and B
are themselves equivalent — and chasing that chain semantically is
fragile. Roots have no upstream refs (depends_on is empty), so equality
is local and safe.

When a dedup happens, the pass records the id→id rewrite in
`ctx.rewrites` so downstream passes (notably AggregatorPass) can track
which terminal-stream id survived.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence

from apps.api.core.logging import get_logger
from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.passes.base import GraphPass, PassContext
from apps.api.runtime.registry import NodeRegistry, node_registry

logger = get_logger(__name__)

_REF = re.compile(r"^\$\{([^}]+)\}$")


class DedupPass(GraphPass):
    name = "dedup"

    def __init__(self, registry: NodeRegistry | None = None) -> None:
        self._registry = registry or node_registry

    def apply(self, graph: WorkflowGraph, ctx: PassContext) -> WorkflowGraph:
        specs = list(graph.nodes.values())
        rewrites = self._compute_root_rewrites(specs)

        if not rewrites:
            return graph

        # Drop merged nodes, rewrite refs everywhere else
        survivors = [s for s in specs if s.id not in rewrites]
        rewritten = [_apply_rewrites(s, rewrites) for s in survivors]

        # Accumulate into ctx so downstream passes can follow the renames
        ctx.rewrites.update(rewrites)
        logger.info(
            "passes.dedup",
            merged=len(rewrites),
            rewrites=rewrites,
        )

        return WorkflowGraph.build(
            id=graph.id,
            version=graph.version,
            nodes=rewritten,
            metadata=graph.metadata,
        )

    # ── internal ────────────────────────────────────────────────────────────

    def _compute_root_rewrites(self, specs: Sequence[NodeSpec]) -> Dict[str, str]:
        """Group root nodes by their canonical dedup key. Each group with
        >1 members yields rewrites (dropped→kept). Nodes whose dedup key
        is None opt out entirely."""
        groups: Dict[bytes, List[str]] = {}
        for spec in specs:
            if spec.depends_on:
                continue
            key = self._dedup_key(spec)
            if key is None:
                continue
            groups.setdefault(key, []).append(spec.id)

        rewrites: Dict[str, str] = {}
        for ids in groups.values():
            if len(ids) <= 1:
                continue
            kept = sorted(ids)[0]
            for dropped in ids:
                if dropped != kept:
                    rewrites[dropped] = kept
        return rewrites

    def _dedup_key(self, spec: NodeSpec) -> bytes | None:
        """Look up the node class and delegate to its canonicalize_dedup_key.
        If the type isn't registered, fall back to structural equality so
        composition still works for test nodes / temporary types."""
        try:
            node_cls = self._registry.resolve(spec.type)
            return node_cls.canonicalize_dedup_key(spec)
        except Exception:
            # Unregistered type — fall back to structural key
            import orjson
            return orjson.dumps((spec.type, spec.config), option=orjson.OPT_SORT_KEYS)


def _apply_rewrites(spec: NodeSpec, rewrites: Mapping[str, str]) -> NodeSpec:
    new_depends = tuple(rewrites.get(d, d) for d in spec.depends_on)
    new_config = _rewrite_node_refs(spec.config, rewrites)
    new_config = _rewrite_plain_inputs(new_config, rewrites)
    return NodeSpec(
        id=spec.id,
        type=spec.type,
        config=new_config,
        depends_on=new_depends,
        emits=spec.emits,
        retries=spec.retries,
        retry_backoff_s=spec.retry_backoff_s,
        timeout_s=spec.timeout_s,
        optional=spec.optional,
    )


def _rewrite_plain_inputs(config: Any, rewrites: Mapping[str, str]) -> Any:
    """FusionNode `inputs` lists bare node ids; follow merges there too."""
    inputs = config.get("inputs") if isinstance(config, Mapping) else None
    if not isinstance(inputs, list):
        return config
    renamed = []
    for i in inputs:
        i = rewrites.get(i, i) if isinstance(i, str) else i
        if i not in renamed:
            renamed.append(i)
    return {**config, "inputs": renamed}


def _rewrite_node_refs(value: Any, rewrites: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        m = _REF.match(value)
        if not m:
            return value
        path = m.group(1)
        head, *rest = path.split(".")
        if head in rewrites:
            return "${" + ".".join([rewrites[head], *rest]) + "}"
        return value
    if isinstance(value, Mapping):
        return {k: _rewrite_node_refs(v, rewrites) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_node_refs(v, rewrites) for v in value]
    return value
