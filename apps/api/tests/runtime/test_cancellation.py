"""
Cancellation propagation: setting execution.cancel must tear down in-flight
nodes and emit WORKFLOW_CANCELLED. Slow nodes must NOT outlive the run.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from apps.api.runtime.events import EventType
from apps.api.runtime.graph import NodeSpec, WorkflowGraph


@pytest.mark.asyncio
async def test_cancellation_aborts_in_flight_nodes(
    make_execution, make_scheduler, collect_events,
):
    graph = WorkflowGraph.build(
        id="cancel", version="1",
        nodes=[
            NodeSpec(id="slow", type="test.slow", config={"sleep_s": 2.0}),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()

    drain = asyncio.create_task(collect_events(exe.events))

    async def cancel_soon():
        await asyncio.sleep(0.05)
        exe.cancel.set()

    cancel_task = asyncio.create_task(cancel_soon())

    t0 = time.monotonic()
    results = await scheduler.run(graph, exe)
    elapsed = time.monotonic() - t0
    await exe.events.close()
    events = await drain
    await cancel_task

    # Run should terminate well before the slow node would have finished
    assert elapsed < 0.5, f"cancellation didn't tear down in-flight node (took {elapsed:.3f}s)"

    cancelled = [e for e in events if e.type == EventType.WORKFLOW_CANCELLED]
    assert len(cancelled) == 1

    # The slow node either never made it into results or was recorded as skipped
    if "slow" in results:
        assert results["slow"].skipped or not results["slow"].ok


@pytest.mark.asyncio
async def test_cancellation_does_not_leak_tasks(
    make_execution, make_scheduler, collect_events,
):
    """After cancellation, no node task should still be running."""
    graph = WorkflowGraph.build(
        id="leak-check", version="1",
        nodes=[
            NodeSpec(id="a", type="test.slow", config={"sleep_s": 3.0}),
            NodeSpec(id="b", type="test.slow", config={"sleep_s": 3.0}),
            NodeSpec(id="c", type="test.slow", config={"sleep_s": 3.0}),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()

    drain = asyncio.create_task(collect_events(exe.events))

    async def cancel_soon():
        await asyncio.sleep(0.05)
        exe.cancel.set()

    cancel_task = asyncio.create_task(cancel_soon())
    await scheduler.run(graph, exe)
    await exe.events.close()
    await drain
    await cancel_task

    # Verify no orphaned node tasks remain in the event loop
    leaked = [
        t for t in asyncio.all_tasks()
        if t.get_name().startswith("node:") and not t.done()
    ]
    assert not leaked, f"leaked {len(leaked)} node tasks after cancellation"


