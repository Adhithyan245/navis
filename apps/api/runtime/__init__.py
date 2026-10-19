"""
Navis Workflow Runtime
======================

Async graph-execution engine. The runtime owns:

  * graph data structures (NodeSpec, WorkflowGraph)
  * the per-execution Blackboard + ExecutionContext
  * the Scheduler (dependency-driven async dispatch)
  * the NodeRegistry (type-string -> Node class)
  * the EventBus (NDJSON streaming pipeline)

It does NOT know about providers, ranking, fusion, or any other domain
concept. Those live in apps/api/runtime/nodes/* and register themselves
against the runtime via NodeRegistry.
"""
from apps.api.runtime.graph import NodeSpec, WorkflowGraph, GraphValidationError
from apps.api.runtime.context import Blackboard, ExecutionContext, NodeContext, NodeResult
from apps.api.runtime.registry import NodeRegistry, node_registry
from apps.api.runtime.scheduler import Scheduler, WorkflowCancelled
from apps.api.runtime.events import EventBus, Event, EventType

__all__ = [
    "NodeSpec",
    "WorkflowGraph",
    "GraphValidationError",
    "Blackboard",
    "ExecutionContext",
    "NodeContext",
    "NodeResult",
    "NodeRegistry",
    "node_registry",
    "Scheduler",
    "WorkflowCancelled",
    "EventBus",
    "Event",
    "EventType",
]
