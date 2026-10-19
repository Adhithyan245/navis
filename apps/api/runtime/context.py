"""
Execution-time context shared between the Scheduler and Nodes.

ExecutionContext: per-workflow-run state (query, user context, blackboard,
event bus, cancel signal).

Blackboard: async-safe key/value store where nodes publish outputs for
downstream nodes to consume.

NodeContext: the per-node view handed to a Node's execute() method —
contains its spec, resolved inputs, and a handle to the shared facilities.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from apps.api.runtime.events import EventBus
    from apps.api.runtime.graph import NodeSpec, WorkflowGraph


class Blackboard:
    """
    Async-safe key/value store for cross-node outputs.

    Nodes write their output under `spec.output_key`. Downstream nodes read
    via `inputs` resolved by the scheduler before execute() is called, so
    direct Blackboard access from within a node is rarely needed — but it's
    available for nodes that want to publish/consume sideband data.
    """
    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def put(self, key: str, value: Any) -> None:
        async with self._lock:
            self._data[key] = value

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._data.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        """Cheap unlocked read — safe for the scheduler between dispatches."""
        return dict(self._data)


@dataclass
class NodeResult:
    """Outcome of a single node execution."""
    node_id: str
    ok: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    attempts: int = 1
    skipped: bool = False


@dataclass
class ExecutionContext:
    """Shared state for one workflow run."""
    workflow_id: str
    run_id: str
    query: str
    user_context: Dict[str, Any] = field(default_factory=dict)
    blackboard: Blackboard = field(default_factory=Blackboard)
    events: "EventBus" = field(default=None)  # set by runner
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_cancelled(self) -> bool:
        return self.cancel.is_set()


@dataclass
class NodeContext:
    """
    Per-node execution context. Constructed by the scheduler immediately
    before invoking a node's execute() — `inputs` is already resolved from
    the node's depends_on.
    """
    execution: ExecutionContext
    spec: "NodeSpec"
    inputs: Dict[str, NodeResult]   # dep id -> its result

    @property
    def query(self) -> str:
        return self.execution.query

    @property
    def user_context(self) -> Dict[str, Any]:
        return self.execution.user_context

    @property
    def events(self) -> "EventBus":
        return self.execution.events

    def cancelled(self) -> bool:
        return self.execution.is_cancelled()

    def input(self, dep_id: str) -> Any:
        """Convenience: get the `output` of a named dependency, or None."""
        res = self.inputs.get(dep_id)
        return res.output if res and res.ok else None
