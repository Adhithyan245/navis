"""
Partial failure: one node failing must NOT destroy the whole workflow.
Downstream nodes that don't require the failed node's output must still run.
"""
from __future__ import annotations

import asyncio

import pytest

from apps.api.runtime.events import EventType
from apps.api.runtime.graph import NodeSpec, WorkflowGraph


@pytest.mark.asyncio
async def test_unrelated_failure_does_not_block_workflow(
    make_execution, make_scheduler, collect_events,
):
    graph = WorkflowGraph.build(
        id="partial-fail", version="1",
        nodes=[
            NodeSpec(id="root", type="test.echo", config={"value": "ok"}),
            NodeSpec(id="bad", type="test.boom", depends_on=("root",)),
            NodeSpec(id="good", type="test.echo", config={"value": "still-ran"}, depends_on=("root",)),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()

    drain = asyncio.create_task(collect_events(exe.events))
    results = await scheduler.run(graph, exe)
    await exe.events.close()
    events = await drain

    assert results["root"].ok
    assert not results["bad"].ok
    assert results["bad"].error == "RuntimeError: boom"
    assert results["good"].ok
    assert results["good"].output == "still-ran"

    # workflow_completed must still fire even though one node failed
    completed = [e for e in events if e.type == EventType.WORKFLOW_COMPLETED]
    assert len(completed) == 1
    assert completed[0].data["failed"] == 1


@pytest.mark.asyncio
async def test_downstream_can_observe_upstream_failure(
    make_execution, make_scheduler, collect_events,
):
    """A node depending on a failed dep still runs; it can see ok=False in inputs."""
    graph = WorkflowGraph.build(
        id="observe-fail", version="1",
        nodes=[
            NodeSpec(id="bad", type="test.boom"),
            NodeSpec(id="watcher", type="test.collect", depends_on=("bad",)),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()
    drain = asyncio.create_task(collect_events(exe.events))
    results = await scheduler.run(graph, exe)
    await exe.events.close()
    await drain

    # watcher's collect-node returned {bad: None} because ctx.input() returns None on failed deps
    assert results["watcher"].ok
    assert results["watcher"].output == {"bad": None}


@pytest.mark.asyncio
async def test_retry_then_succeed(
    make_execution, make_scheduler, collect_events,
):
    graph = WorkflowGraph.build(
        id="retry-then-succeed", version="1",
        nodes=[
            NodeSpec(
                id="flaky", type="test.fail_once",
                config={"fail_until_attempt": 2},
                retries=3, retry_backoff_s=0.01,
            ),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()
    drain = asyncio.create_task(collect_events(exe.events))
    results = await scheduler.run(graph, exe)
    await exe.events.close()
    await drain

    assert results["flaky"].ok
    assert results["flaky"].attempts == 3
    assert results["flaky"].output == {"attempts": 3}


@pytest.mark.asyncio
async def test_retry_exhaustion_marks_failed(
    make_execution, make_scheduler, collect_events,
):
    graph = WorkflowGraph.build(
        id="retry-exhaust", version="1",
        nodes=[
            NodeSpec(
                id="flaky", type="test.fail_once",
                config={"fail_until_attempt": 10},
                retries=2, retry_backoff_s=0.01,
            ),
        ],
    )
    exe = make_execution()
    scheduler = make_scheduler()
    drain = asyncio.create_task(collect_events(exe.events))
    results = await scheduler.run(graph, exe)
    await exe.events.close()
    await drain

    assert not results["flaky"].ok
    assert results["flaky"].attempts == 3  # initial + 2 retries
    assert "engineered failure" in results["flaky"].error
