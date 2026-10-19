"""
Workflow graph data structures.

A WorkflowGraph is an immutable, validated DAG. The compiler produces these
from YAML/JSON workflow definitions; the Scheduler consumes them. Graphs
contain no execution state — that lives in ExecutionContext.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class GraphValidationError(Exception):
    """Raised when a WorkflowGraph fails structural validation."""


@dataclass(frozen=True)
class NodeSpec:
    """
    Declarative specification of one node in a workflow graph.

    The runtime knows nothing about what `type` means — that's resolved at
    schedule time by the NodeRegistry. `config` is opaque to the runtime
    and passed through to the Node implementation.
    """
    id: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)
    depends_on: Tuple[str, ...] = ()
    emits: Optional[str] = None          # blackboard key; defaults to node id
    retries: int = 0
    retry_backoff_s: float = 0.5
    timeout_s: Optional[float] = None
    optional: bool = False                # if True, failure does not block downstream

    @property
    def output_key(self) -> str:
        return self.emits or self.id


@dataclass(frozen=True)
class WorkflowGraph:
    """
    A validated DAG of NodeSpecs. Construct via WorkflowGraph.build() — the
    constructor does not validate, so direct dataclass instantiation is for
    internal use only.
    """
    id: str
    version: str
    nodes: Dict[str, NodeSpec]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        id: str,
        version: str,
        nodes: List[NodeSpec],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "WorkflowGraph":
        node_map: Dict[str, NodeSpec] = {}
        for spec in nodes:
            if spec.id in node_map:
                raise GraphValidationError(f"duplicate node id: {spec.id!r}")
            node_map[spec.id] = spec

        # Reference + cycle validation
        for spec in node_map.values():
            for dep in spec.depends_on:
                if dep not in node_map:
                    raise GraphValidationError(
                        f"node {spec.id!r} depends on unknown node {dep!r}"
                    )
                if dep == spec.id:
                    raise GraphValidationError(
                        f"node {spec.id!r} depends on itself"
                    )

        graph = cls(id=id, version=version, nodes=node_map, metadata=metadata or {})
        graph._detect_cycle()
        return graph

    # ── traversal helpers ─────────────────────────────────────────────────

    def roots(self) -> List[str]:
        """Nodes with no dependencies — the initial ready set."""
        return [nid for nid, spec in self.nodes.items() if not spec.depends_on]

    def successors(self, node_id: str) -> List[str]:
        """All nodes that directly depend on `node_id`."""
        return [
            nid for nid, spec in self.nodes.items()
            if node_id in spec.depends_on
        ]

    # ── internal ──────────────────────────────────────────────────────────

    def _detect_cycle(self) -> None:
        """
        DFS-based cycle detection. Raises GraphValidationError on first cycle
        with the participating node ids.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in self.nodes}
        stack: List[str] = []

        def visit(nid: str) -> None:
            color[nid] = GRAY
            stack.append(nid)
            for dep in self.nodes[nid].depends_on:
                if color[dep] == GRAY:
                    cycle_start = stack.index(dep)
                    cycle = stack[cycle_start:] + [dep]
                    raise GraphValidationError(
                        f"cycle detected: {' -> '.join(cycle)}"
                    )
                if color[dep] == WHITE:
                    visit(dep)
            stack.pop()
            color[nid] = BLACK

        for nid in self.nodes:
            if color[nid] == WHITE:
                visit(nid)
