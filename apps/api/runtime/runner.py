"""
Runner — the high-level facade routes use to execute workflows.

Two public entry points:

  * `run_workflow_ndjson(name, query, ...)` — execute a single named
    workflow. Used by POST /v2/workflow/{name}.

  * `run_query_ndjson(query, ...)` — analyze the query's intent, compose
    the matched workflows into a single graph, execute that. Used by
    POST /v2/query.

Both return async generators of NDJSON byte lines (StreamingResponse-ready)
and share the same execution machinery via `_execute_graph_ndjson`.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

from apps.api.core.logging import get_logger
from apps.api.runtime.compiler.registry import WorkflowNotFound, workflow_registry
from apps.api.runtime.compose import ComposerError, compose_graphs
from apps.api.runtime.context import ExecutionContext
from apps.api.runtime.events import EventBus, EventType
from apps.api.runtime.graph import WorkflowGraph
from apps.api.runtime.intent import IntentAnalyzer, IntentMatch, intent_analyzer
from apps.api.runtime.scheduler import Scheduler
from apps.api.runtime.view import external_stream

logger = get_logger(__name__)


async def run_workflow_ndjson(
    workflow_name: str,
    query: str,
    user_context: Optional[Dict[str, Any]] = None,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    heartbeat_interval_s: float = 5.0,
    event_queue_maxsize: int = 256,
) -> AsyncIterator[bytes]:
    """Execute a single registered workflow by name. Streams user-facing NDJSON."""
    graph = workflow_registry.get(workflow_name)
    async for line in _execute_graph_ndjson(
        graph, query, user_context or {},
        metadata=metadata, run_id=run_id,
        heartbeat_interval_s=heartbeat_interval_s,
        event_queue_maxsize=event_queue_maxsize,
    ):
        yield line


async def run_query_ndjson(
    query: str,
    user_context: Optional[Dict[str, Any]] = None,
    *,
    analyzer: Optional[IntentAnalyzer] = None,
    max_workflows: int = 3,
    metadata: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    heartbeat_interval_s: float = 5.0,
    event_queue_maxsize: int = 256,
) -> AsyncIterator[bytes]:
    """
    Full /v2/query pipeline: analyze intent → resolve workflows → compose
    → execute → stream user-facing NDJSON.

    Intent reasoning is internal and never leaks to the wire. If no
    intent matches resolve to known workflows, an `error` event is the
    only thing emitted to the client.
    """
    a = analyzer or intent_analyzer
    matches: List[IntentMatch] = await a.analyze(query, user_context or {})
    selected: List[WorkflowGraph] = []
    selection_log: List[Dict[str, Any]] = []
    for match in matches[:max_workflows]:
        try:
            graph = workflow_registry.get(match.workflow)
        except WorkflowNotFound:
            logger.warning(
                "intent.unknown_workflow",
                workflow=match.workflow,
                reason=match.reason,
            )
            continue
        selected.append(graph)
        selection_log.append({
            "workflow": match.workflow,
            "confidence": match.confidence,
            "reason": match.reason,
        })

    if not selected:
        logger.error("query.no_workflows_resolved", query=query, matches=[m.workflow for m in matches])
        # Emit a minimal scrubbed error stream so the route sees something
        async for line in _emit_terminal_error(
            run_id=run_id or uuid.uuid4().hex,
            message="No workflow could handle that request.",
        ):
            yield line
        return

    logger.info("query.intent_resolved", query=query, selection=selection_log)

    try:
        composed = compose_graphs(selected, composed_id="query_composed")
    except ComposerError as exc:
        logger.error("query.compose_failed", error=str(exc))
        async for line in _emit_terminal_error(
            run_id=run_id or uuid.uuid4().hex,
            message="We couldn't assemble that request. Please try again.",
        ):
            yield line
        return

    composed_meta = {
        **(metadata or {}),
        "intent_selection": selection_log,
    }

    async for line in _execute_graph_ndjson(
        composed, query, user_context or {},
        metadata=composed_meta, run_id=run_id,
        heartbeat_interval_s=heartbeat_interval_s,
        event_queue_maxsize=event_queue_maxsize,
    ):
        yield line


# ── shared execution path ───────────────────────────────────────────────────

async def _execute_graph_ndjson(
    graph: WorkflowGraph,
    query: str,
    user_context: Dict[str, Any],
    *,
    metadata: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    heartbeat_interval_s: float = 5.0,
    event_queue_maxsize: int = 256,
) -> AsyncIterator[bytes]:
    """
    Inner loop shared by both public runners. Owns the EventBus +
    Scheduler task lifecycle and cancellation propagation.
    """
    run_id = run_id or uuid.uuid4().hex

    bus = EventBus(
        run_id=run_id,
        maxsize=event_queue_maxsize,
        heartbeat_interval_s=heartbeat_interval_s,
    )
    execution = ExecutionContext(
        workflow_id=graph.id,
        run_id=run_id,
        query=query,
        user_context=user_context,
        events=bus,
        metadata=metadata or {},
    )

    scheduler = Scheduler()
    bus.start()

    scheduler_task = asyncio.create_task(
        _run_with_close(scheduler, graph, execution, bus),
        name=f"scheduler:{graph.id}:{run_id}",
    )

    try:
        async for line in external_stream(bus):
            yield line
    except asyncio.CancelledError:
        execution.cancel.set()
        raise
    finally:
        if not scheduler_task.done():
            execution.cancel.set()
            try:
                await asyncio.wait_for(scheduler_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                scheduler_task.cancel()
                try:
                    await scheduler_task
                except (asyncio.CancelledError, Exception):
                    pass


async def _run_with_close(
    scheduler: Scheduler, graph: WorkflowGraph,
    execution: ExecutionContext, bus: EventBus,
) -> None:
    try:
        await scheduler.run(graph, execution)
    except Exception as exc:
        logger.error(
            "workflow scheduler crashed",
            workflow=graph.id, run_id=execution.run_id, error=str(exc),
        )
        try:
            await bus.emit(
                EventType.WORKFLOW_FAILED,
                {"workflow": graph.id, "run_id": execution.run_id, "error": str(exc)},
            )
        except Exception:
            pass
    finally:
        await bus.close()


async def _emit_terminal_error(*, run_id: str, message: str) -> AsyncIterator[bytes]:
    """Single-event NDJSON stream for terminal pre-execution failures."""
    bus = EventBus(run_id=run_id, heartbeat_interval_s=60.0)
    await bus.emit(EventType.WORKFLOW_FAILED, {"error": message})
    await bus.close()
    async for line in external_stream(bus):
        yield line
