"""
AggregatorPass — append the single composed final_stream node.

Reads `ctx.metadata['ingest.terminals']` (set by IngestPass) for the list
of (source_workflow_id, namespaced_terminal_id) pairs, applies any dedup
rewrites accumulated in `ctx.rewrites`, and emits one stream node that
depends on every surviving terminal.

The aggregator's payload contains a `sections` list keyed by each source
workflow's `metadata.section_kind` — a user-friendly category label
("places", "events", "work", ...), never the workflow id itself. This
keeps invisible-orchestration intact in the composed wire payload.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.passes.base import GraphPass, PassContext

AGGREGATOR_ID = "__composed__final_stream"


class AggregatorPass(GraphPass):
    name = "aggregator"

    def apply(self, graph: WorkflowGraph, ctx: PassContext) -> WorkflowGraph:
        terminals: List[Tuple[str, str]] = ctx.metadata.get("ingest.terminals", [])

        # Apply accumulated dedup rewrites so terminal ids stay valid
        if ctx.rewrites:
            terminals = [(wf, ctx.rewrites.get(t, t)) for wf, t in terminals]

        if not terminals:
            # No source workflow terminated in a stream — nothing to aggregate.
            return graph

        sections = []
        for source in ctx.source_workflows:
            ns_terminal = next((t for wf, t in terminals if wf == source.id), None)
            if ns_terminal is None:
                continue
            sections.append({
                "kind": _section_kind(source),
                "data": "${" + ns_terminal + "}",
            })

        aggregator = NodeSpec(
            id=AGGREGATOR_ID,
            type="stream",
            depends_on=tuple(t for _, t in terminals),
            config={
                "payload": {
                    "query": "${ctx.query}",
                    "sections": sections,
                },
            },
        )

        return WorkflowGraph.build(
            id=graph.id,
            version=graph.version,
            nodes=[*graph.nodes.values(), aggregator],
            metadata={
                **graph.metadata,
                "section_kinds": [_section_kind(g) for g in ctx.source_workflows],
            },
        )


def _section_kind(source: WorkflowGraph) -> str:
    """User-friendly section label from metadata; falls back to workflow id
    (which is never user-facing — the aggregator's wire payload uses these
    labels, so workflows SHOULD set section_kind)."""
    kind = source.metadata.get("section_kind") if source.metadata else None
    return str(kind) if kind else source.id
