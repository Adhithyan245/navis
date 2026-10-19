"""
Scheduler — dependency-driven async dispatch for a WorkflowGraph.

Execution model
---------------
* Nodes become "ready" the moment all of their `depends_on` entries have
  finished, regardless of success or failure. A node that *requires* a
  successful upstream result must check `ctx.inputs[dep].ok` itself.
* Ready nodes run concurrently as asyncio.Tasks. There is no rigid stage
  boundary — as soon as one node finishes, any newly-unblocked node is
  dispatched, even while sibling nodes are still running.
* A node that raises (after exhausting retries) does NOT halt the workflow:
  its slot is filled with a failed NodeResult and the scheduler continues
  with whatever downstream nodes can still run.
* A node whose dependency was *cancelled* (not failed — cancelled) is
  itself skipped, because we can't honour its contract.
* Cancellation propagates from ExecutionContext.cancel. All in-flight tasks
  are cancelled; the run terminates with a WorkflowCancelled event.

The scheduler emits lifecycle events through ExecutionContext.events but
returns the full results map to the caller. Streaming consumers should
subscribe to the EventBus rather than wait for the return value.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, Optional, Set

from apps.api.core.logging import get_logger
from apps.api.runtime.context import ExecutionContext, NodeContext, NodeResult
from apps.api.runtime.events import EventType
from apps.api.runtime.graph import WorkflowGraph
from apps.api.runtime.registry import NodeRegistry, node_registry

logger = get_logger(__name__)


class WorkflowCancelled(Exception):
    """Raised internally when the run is cancelled before completion."""


class Scheduler:
    def __init__(self, registry: Optional[NodeRegistry] = None) -> None:
        self._registry = registry or node_registry

    async def run(
        self,
        graph: WorkflowGraph,
        execution: ExecutionContext,
    ) -> Dict[str, NodeResult]:
        """
        Execute `graph` against `execution`. Returns the full {node_id: NodeResult}
        map. Lifecycle events flow through execution.events.
        """
        if execution.events is None:
            raise RuntimeError("ExecutionContext.events must be set before scheduler.run()")

        results: Dict[str, NodeResult] = {}
        completed: Set[str] = set()
        in_flight: Dict[str, asyncio.Task] = {}
        done_queue: asyncio.Queue[NodeResult] = asyncio.Queue()
        cancel_waiter = asyncio.create_task(execution.cancel.wait())

        await execution.events.emit(
            EventType.WORKFLOW_STARTED,
            {"workflow": graph.id, "version": graph.version, "run_id": execution.run_id, "nodes": list(graph.nodes)},
        )

        def ready_nodes() -> list[str]:
            out = []
            for nid, spec in graph.nodes.items():
                if nid in completed or nid in in_flight:
                    continue
                if all(dep in completed for dep in spec.depends_on):
                    out.append(nid)
            return out

        def dispatch_ready() -> None:
            for nid in ready_nodes():
                spec = graph.nodes[nid]
                # Skip if any required dep was cancelled (not merely failed)
                skipped_due_to_cancelled_dep = False
                for dep in spec.depends_on:
                    dep_res = results.get(dep)
                    if dep_res is not None and dep_res.skipped:
                        skipped_due_to_cancelled_dep = True
                        break
                if skipped_due_to_cancelled_dep:
                    skip_result = NodeResult(
                        node_id=nid, ok=False, skipped=True,
                        error="upstream dependency was cancelled",
                    )
                    results[nid] = skip_result
                    completed.add(nid)
                    asyncio.create_task(
                        execution.events.emit(
                            EventType.NODE_SKIPPED,
                            {"node_id": nid, "reason": skip_result.error},
                        )
                    )
                    continue

                inputs = {dep: results[dep] for dep in spec.depends_on}
                task = asyncio.create_task(
                    self._run_node(graph, spec, execution, inputs, done_queue),
                    name=f"node:{nid}",
                )
                in_flight[nid] = task

        try:
            dispatch_ready()
            if not in_flight:
                # Graph has no nodes or all nodes have unsatisfiable deps —
                # either way, nothing to do.
                await execution.events.emit(
                    EventType.WORKFLOW_COMPLETED,
                    {"workflow": graph.id, "run_id": execution.run_id, "nodes": 0},
                )
                return results

            while in_flight:
                get_task = asyncio.create_task(done_queue.get())
                done, pending = await asyncio.wait(
                    {get_task, cancel_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if cancel_waiter in done:
                    get_task.cancel()
                    raise WorkflowCancelled()

                result: NodeResult = get_task.result()
                results[result.node_id] = result
                completed.add(result.node_id)
                in_flight.pop(result.node_id, None)
                dispatch_ready()

            await execution.events.emit(
                EventType.WORKFLOW_COMPLETED,
                {
                    "workflow": graph.id,
                    "run_id": execution.run_id,
                    "nodes": len(results),
                    "failed": sum(1 for r in results.values() if not r.ok and not r.skipped),
                    "skipped": sum(1 for r in results.values() if r.skipped),
                },
            )
            return results

        except WorkflowCancelled:
            logger.info("workflow cancelled", workflow=graph.id, run_id=execution.run_id)
            for task in in_flight.values():
                task.cancel()
            await asyncio.gather(*in_flight.values(), return_exceptions=True)
            await execution.events.emit(
                EventType.WORKFLOW_CANCELLED,
                {"workflow": graph.id, "run_id": execution.run_id},
            )
            return results
        finally:
            cancel_waiter.cancel()
            # Drain any stragglers that pushed to the queue after cancellation
            while not done_queue.empty():
                try:
                    done_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    # ── internal ──────────────────────────────────────────────────────────

    async def _run_node(
        self,
        graph: WorkflowGraph,
        spec,
        execution: ExecutionContext,
        inputs: Dict[str, NodeResult],
        done_queue: asyncio.Queue,
    ) -> None:
        """Resolve, execute, retry, and push the NodeResult onto done_queue."""
        start = time.monotonic()
        attempts = 0
        last_error: Optional[str] = None
        result: Optional[NodeResult] = None

        try:
            node_cls = self._registry.resolve(spec.type)
        except Exception as exc:
            result = NodeResult(
                node_id=spec.id, ok=False, error=f"resolve failed: {exc}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            await execution.events.emit(
                EventType.NODE_FAILED,
                {"node_id": spec.id, "error": result.error},
            )
            await done_queue.put(result)
            return

        node = node_cls(spec)
        ctx = NodeContext(execution=execution, spec=spec, inputs=inputs)

        await execution.events.emit(
            EventType.NODE_STARTED,
            {"node_id": spec.id, "type": spec.type},
        )

        max_attempts = max(1, spec.retries + 1)
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                if spec.timeout_s is not None:
                    output = await asyncio.wait_for(node.execute(ctx), timeout=spec.timeout_s)
                else:
                    output = await node.execute(ctx)

                result = NodeResult(
                    node_id=spec.id, ok=True, output=output,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    attempts=attempts,
                )
                await execution.blackboard.put(spec.output_key, output)
                await execution.events.emit(
                    EventType.NODE_COMPLETED,
                    {
                        "node_id": spec.id,
                        "type": spec.type,
                        "duration_ms": result.duration_ms,
                        "attempts": attempts,
                    },
                )
                break

            except asyncio.CancelledError:
                # Surface as a skipped result so downstream gets the signal
                result = NodeResult(
                    node_id=spec.id, ok=False, skipped=True,
                    error="cancelled",
                    duration_ms=int((time.monotonic() - start) * 1000),
                    attempts=attempts,
                )
                await execution.events.emit(
                    EventType.NODE_SKIPPED,
                    {"node_id": spec.id, "reason": "cancelled"},
                )
                # Bubble the cancellation so the gather() in scheduler.run sees it
                await done_queue.put(result)
                raise

            except asyncio.TimeoutError:
                last_error = f"timeout after {spec.timeout_s}s"
                logger.warning("node timeout", node_id=spec.id, attempt=attempt)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("node failed", node_id=spec.id, attempt=attempt, error=last_error)

            if attempt < max_attempts:
                backoff = spec.retry_backoff_s * (2 ** (attempt - 1))
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    # Don't bother retrying if we're being torn down
                    raise

        if result is None:
            result = NodeResult(
                node_id=spec.id, ok=False, error=last_error or "unknown failure",
                duration_ms=int((time.monotonic() - start) * 1000),
                attempts=attempts,
            )
            await execution.events.emit(
                EventType.NODE_FAILED,
                {
                    "node_id": spec.id, "type": spec.type,
                    "error": result.error, "attempts": attempts,
                    "duration_ms": result.duration_ms,
                },
            )

        await done_queue.put(result)
