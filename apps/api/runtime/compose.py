"""
compose_graphs — thin pipeline runner.

All composition logic now lives in `apps/api/runtime/passes/*`. This file
defines the pipeline order and exposes the public `compose_graphs`
function that runs it.

Pipeline (in order):

  IngestPass          → namespace nodes; flip terminal streams to partial
  DedupPass           → semantic root-node dedup via Node.canonicalize_dedup_key
  ContractValidatePass → opt-in NodeContract validation (fail-fast)
  AggregatorPass      → append single composed final_stream node

External API is unchanged from the previous monolithic composer; existing
tests and routes continue to work without modification.
"""
from __future__ import annotations

from typing import Sequence

from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.passes import (
    AggregatorPass,
    ContractValidatePass,
    DedupPass,
    GraphPass,
    IngestPass,
    PassContext,
    PassError,
)
from apps.api.runtime.passes.aggregator import AGGREGATOR_ID  # re-export for tests

# Backwards-compat alias — older tests imported _AGGREGATOR_ID with the
# leading underscore from the monolithic composer.
_AGGREGATOR_ID = AGGREGATOR_ID

# Backwards-compat: composer-level error type
ComposerError = PassError


_DEFAULT_PIPELINE: tuple[GraphPass, ...] = (
    IngestPass(),
    DedupPass(),
    ContractValidatePass(),
    AggregatorPass(),
)


def compose_graphs(
    graphs: Sequence[WorkflowGraph],
    *,
    composed_id: str = "composed",
    pipeline: Sequence[GraphPass] = _DEFAULT_PIPELINE,
) -> WorkflowGraph:
    """
    Merge `graphs` into a single executable WorkflowGraph by running the
    pipeline. With one graph: returns unchanged.

    `pipeline` is overridable — tests can swap in custom pass orderings
    or skip specific passes; production callers use the default.
    """
    if not graphs:
        raise PassError("compose_graphs requires at least one graph")
    if len(graphs) == 1:
        return graphs[0]

    ctx = PassContext(source_workflows=list(graphs))

    # Seed graph for the pipeline — empty, gets populated by IngestPass.
    graph = WorkflowGraph.build(
        id=composed_id,
        version="composed",
        nodes=[NodeSpec(id="__seed__", type="__seed__")],
        metadata={},
    )
    # The seed is a placeholder so WorkflowGraph.build doesn't reject an
    # empty list; IngestPass discards it by returning a freshly-built graph.

    for pass_ in pipeline:
        graph = pass_.apply(graph, ctx)

    return graph
