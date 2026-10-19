"""Per-node timeout enforcement."""
from __future__ import annotations

import asyncio
import pytest

from apps.api.runtime.graph import NodeSpec, WorkflowGraph


@pytest.mark.asyncio
async def test_node_timeout_marks_failure(
    make_execution, make_scheduler, collect_events,
):
    graph = WorkflowGraph.build(
        id="timeout", version="1",
        nodes=[
            NodeSpec(
                id="slow", type="test.slow",
                config={"sleep_s": 5.0},
                timeout_s=0.1,
            ),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()
    drain = asyncio.create_task(collect_events(exe.events))
    results = await scheduler.run(graph, exe)
    await exe.events.close()
    await drain

    assert not results["slow"].ok
    assert "timeout" in (results["slow"].error or "").lower()


@pytest.mark.asyncio
async def test_timeout_does_not_block_siblings(
    make_execution, make_scheduler, collect_events,
):
    """A timing-out node must not delay other parallel-ready nodes."""
    import time
    graph = WorkflowGraph.build(
        id="timeout-sibling", version="1",
        nodes=[
            NodeSpec(id="slow", type="test.slow", config={"sleep_s": 5.0}, timeout_s=0.1),
            NodeSpec(id="fast", type="test.echo", config={"value": "fast"}),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()
    drain = asyncio.create_task(collect_events(exe.events))

    t0 = time.monotonic()
    results = await scheduler.run(graph, exe)
    elapsed = time.monotonic() - t0
    await exe.events.close()
    await drain

    assert elapsed < 0.5
    assert results["fast"].ok
    assert not results["slow"].ok
