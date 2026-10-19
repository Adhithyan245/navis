"""
IngestPass — turn N source workflows into a single namespaced graph.

This is the "seed" pass: it ignores the input graph (passed as a sentinel
empty graph by the pipeline runner) and reads `ctx.source_workflows`
instead. The output is a graph containing every source workflow's nodes,
with ids prefixed `{workflow_id}__` and all local `${...}` references
rewritten to match.

The pass also flips each source workflow's terminal stream node to
`partial: true`, so that the eventual composed aggregator (added by
AggregatorPass) is the only emitter of a `final_result` event.
"""
from __future__ import annotations

import re
from typing import Any, List, Mapping

from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.passes.base import GraphPass, PassContext, PassError

_REF = re.compile(r"^\$\{([^}]+)\}$")


class IngestPass(GraphPass):
    name = "ingest"

    def apply(self, graph: WorkflowGraph, ctx: PassContext) -> WorkflowGraph:
        if not ctx.source_workflows:
            raise PassError("IngestPass requires ctx.source_workflows")

        namespaced: List[NodeSpec] = []
        terminals: List[tuple[str, str]] = []   # (source_workflow_id, namespaced_terminal_id)

        for source in ctx.source_workflows:
            prefix = f"{source.id}__"
            local_ids = set(source.nodes)
            terminal_id = _find_terminal_stream(source)

            for spec in source.nodes.values():
                new_config = _rewrite_local_refs(spec.config, prefix, local_ids)
                new_config = _rewrite_plain_inputs(new_config, lambda i: prefix + i if i in local_ids else i)
                if spec.id == terminal_id:
                    new_config = {**new_config, "partial": True}

                namespaced.append(NodeSpec(
                    id=prefix + spec.id,
                    type=spec.type,
                    config=new_config,
                    depends_on=tuple(prefix + d for d in spec.depends_on),
                    emits=spec.emits,
                    retries=spec.retries,
                    retry_backoff_s=spec.retry_backoff_s,
                    timeout_s=spec.timeout_s,
                    optional=spec.optional,
                ))

            if terminal_id:
                terminals.append((source.id, prefix + terminal_id))

        ctx.metadata["ingest.terminals"] = terminals
        ctx.metadata["ingest.workflow_ids"] = [g.id for g in ctx.source_workflows]

        return WorkflowGraph.build(
            id=graph.id,
            version=graph.version,
            nodes=namespaced,
            metadata={
                **graph.metadata,
                "source_workflows": [g.id for g in ctx.source_workflows],
            },
        )


# ── helpers ─────────────────────────────────────────────────────────────────

def _find_terminal_stream(graph: WorkflowGraph) -> str | None:
    """Workflow's lone terminal stream node: type='stream', no successors,
    not already marked partial. None means the workflow doesn't terminate
    in a stream (still composable; it just contributes no aggregator section)."""
    has_successor: set[str] = set()
    for spec in graph.nodes.values():
        for dep in spec.depends_on:
            has_successor.add(dep)

    candidates = [
        spec.id for spec in graph.nodes.values()
        if spec.type == "stream"
        and spec.id not in has_successor
        and not spec.config.get("partial", False)
    ]
    if not candidates:
        return None
    if len(candidates) > 1:
        raise PassError(
            f"workflow {graph.id!r} has multiple terminal stream nodes: "
            f"{sorted(candidates)} (composer requires exactly one)"
        )
    return candidates[0]


def _rewrite_plain_inputs(config: Mapping[str, Any], rename) -> Mapping[str, Any]:
    """FusionNode's `inputs` is a list of bare node ids (not `${...}` refs),
    so `_rewrite_local_refs` leaves it alone. Rename those ids too, or the
    fusion node filters out every (namespaced) dependency."""
    inputs = config.get("inputs") if isinstance(config, Mapping) else None
    if not isinstance(inputs, list):
        return config
    return {**config, "inputs": [rename(i) if isinstance(i, str) else i for i in inputs]}


def _rewrite_local_refs(value: Any, prefix: str, local_ids: set[str]) -> Any:
    """Rewrite `${id.path}` to `${prefix+id.path}` for ids in `local_ids`.
    `${ctx.*}` is left alone; refs to unknown ids likewise."""
    if isinstance(value, str):
        m = _REF.match(value)
        if not m:
            return value
        path = m.group(1)
        head, *rest = path.split(".")
        if head in local_ids:
            return "${" + ".".join([prefix + head, *rest]) + "}"
        return value
    if isinstance(value, Mapping):
        return {k: _rewrite_local_refs(v, prefix, local_ids) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_local_refs(v, prefix, local_ids) for v in value]
    return value
