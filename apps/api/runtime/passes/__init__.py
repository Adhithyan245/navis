"""
Graph passes — composable transformations from WorkflowGraph to WorkflowGraph.

The compose pipeline is a sequence of passes, each independently testable.
Adding a new transformation = writing a new pass and dropping it into the
pipeline order. No god-object composer.

Pass execution model:

  initial_graph = ingest(source_workflows)   # IngestPass-like seed step
  for pass in pipeline:
      graph = pass.apply(graph, ctx)
  return graph

`PassContext` carries cross-pass state (source workflows, accumulated
dedup rewrites, traces) without polluting WorkflowGraph itself.
"""
from apps.api.runtime.passes.base import GraphPass, PassContext, PassError
from apps.api.runtime.passes.ingest import IngestPass
from apps.api.runtime.passes.dedup import DedupPass
from apps.api.runtime.passes.aggregator import AggregatorPass
from apps.api.runtime.passes.contract_validate import ContractValidatePass

__all__ = [
    "GraphPass",
    "PassContext",
    "PassError",
    "IngestPass",
    "DedupPass",
    "AggregatorPass",
    "ContractValidatePass",
]
