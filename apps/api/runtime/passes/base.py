"""
GraphPass ABC + PassContext.

Each pass is a pure function from (WorkflowGraph, PassContext) to a new
WorkflowGraph. Passes never mutate their input graph (WorkflowGraph is
frozen anyway); they construct and return a new one.

PassContext is the only mutable state shared across the pipeline. Use it
for cross-pass communication: source workflows for the IngestPass, dedup
rewrites for AggregatorPass to track, etc.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from apps.api.runtime.graph import WorkflowGraph


class PassError(Exception):
    """Raised when a pass cannot proceed (malformed input, contract violation, etc.)."""


@dataclass
class PassContext:
    """
    State shared across passes for a single composition run.

    `source_workflows`  — the original input graphs, in pipeline order.
                          IngestPass consumes this; later passes may read
                          it for metadata (e.g. section labels).
    `rewrites`          — accumulated id→id rewrites from passes that
                          collapse nodes (DedupPass primarily). Later
                          passes use this to keep their node references
                          in sync.
    `metadata`          — free-form key/value sidecar for traces, metrics,
                          and pass-specific scratch space.
    """
    source_workflows: List[WorkflowGraph] = field(default_factory=list)
    rewrites: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class GraphPass(ABC):
    """One step in the compose pipeline."""

    name: str = ""

    @abstractmethod
    def apply(self, graph: WorkflowGraph, ctx: PassContext) -> WorkflowGraph:
        """Return a new graph derived from `graph`. Must not mutate input."""
