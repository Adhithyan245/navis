"""
Dependency-order tests: nodes must observe their declared inputs and the
scheduler must dispatch parallel-ready nodes concurrently.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from apps.api.runtime.events import EventType
from apps.api.runtime.graph import NodeSpec, WorkflowGraph


@pytest.mark.asyncio
async def test_linear_chain_executes_in_order(make_execution, make_scheduler, collect_events):
    graph = WorkflowGraph.build(
        id="linear", version="1",
        nodes=[
            NodeSpec(id="a", type="test.echo", config={"value": 1}),
            NodeSpec(id="b", type="test.echo", config={"value": 2}, depends_on=("a",)),
            NodeSpec(id="c", type="test.collect", depends_on=("a", "b")),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()

    drain = asyncio.create_task(collect_events(exe.events))
    results = await scheduler.run(graph, exe)
    await exe.events.close()
    events = await drain

    assert results["c"].ok
    assert results["c"].output == {"a": 1, "b": 2}

    started_order = [
        e.data["node_id"] for e in events
        if e.type == EventType.NODE_STARTED
    ]
    assert started_order == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_parallel_siblings_run_concurrently(make_execution, make_scheduler, collect_events):
    """If two nodes have no inter-dep, they must overlap in wall time."""
    graph = WorkflowGraph.build(
        id="diamond", version="1",
        nodes=[
            NodeSpec(id="root", type="test.echo", config={"value": 0}),
            NodeSpec(id="left", type="test.echo", config={"value": "L", "sleep_s": 0.2}, depends_on=("root",)),
            NodeSpec(id="right", type="test.echo", config={"value": "R", "sleep_s": 0.2}, depends_on=("root",)),
            NodeSpec(id="sink", type="test.collect", depends_on=("left", "right")),
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

    assert results["sink"].ok
    # Sequential would be 0.4s+. Parallel should comfortably finish under 0.35s.
    assert elapsed < 0.35, f"parallel siblings ran sequentially (took {elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_graph_validation_catches_cycle():
    from apps.api.runtime.graph import GraphValidationError
    with pytest.raises(GraphValidationError, match="cycle"):
        WorkflowGraph.build(
            id="bad", version="1",
            nodes=[
                NodeSpec(id="a", type="test.echo", depends_on=("b",)),
                NodeSpec(id="b", type="test.echo", depends_on=("a",)),
            ],
        )


@pytest.mark.asyncio
async def test_graph_validation_catches_missing_dep():
    from apps.api.runtime.graph import GraphValidationError
    with pytest.raises(GraphValidationError, match="unknown node"):
        WorkflowGraph.build(
            id="bad", version="1",
            nodes=[NodeSpec(id="a", type="test.echo", depends_on=("ghost",))],
        )
