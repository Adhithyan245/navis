"""
Shared fixtures + tiny test-only Node implementations.

The runtime tests deliberately do NOT exercise the real provider/fusion/
ranking/humanization services — those have their own tests. Here we want
to validate the runtime *itself*: dependency scheduling, cancellation,
retries, view filtering, backpressure.

So we register a few cheap test-only node types (`test.echo`,
`test.fail`, `test.slow`, `test.boom`) that we compose into graphs.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, List

import pytest

from apps.api.runtime.context import ExecutionContext, NodeContext
from apps.api.runtime.events import EventBus
from apps.api.runtime.graph import NodeSpec, WorkflowGraph
from apps.api.runtime.nodes.base import Node
from apps.api.runtime.registry import NodeRegistry
from apps.api.runtime.scheduler import Scheduler


# ── Test-only Node implementations ──────────────────────────────────────────

class EchoNode(Node):
    """Returns the value from spec.config['value'], optionally after a sleep."""
    async def execute(self, ctx: NodeContext) -> Any:
        sleep_s = float(self.spec.config.get("sleep_s", 0))
        if sleep_s:
            await asyncio.sleep(sleep_s)
        return self.spec.config.get("value")


class FailOnceNode(Node):
    """Fails on the first N attempts then succeeds. State stored per-spec.id in a module dict."""
    _attempt_counts: dict = {}

    async def execute(self, ctx: NodeContext) -> Any:
        key = self.spec.id
        count = FailOnceNode._attempt_counts.get(key, 0) + 1
        FailOnceNode._attempt_counts[key] = count
        fail_until = int(self.spec.config.get("fail_until_attempt", 1))
        if count <= fail_until:
            raise RuntimeError(f"engineered failure attempt {count}")
        return {"attempts": count}


class BoomNode(Node):
    """Always raises."""
    async def execute(self, ctx: NodeContext) -> Any:
        raise RuntimeError("boom")


class SlowNode(Node):
    """Sleeps long enough to be cancelled."""
    async def execute(self, ctx: NodeContext) -> Any:
        await asyncio.sleep(self.spec.config.get("sleep_s", 5.0))
        return "should-not-reach"


class CollectInputsNode(Node):
    """Returns the dict of dep_id -> dep.output for verification of dependency order."""
    async def execute(self, ctx: NodeContext) -> Any:
        return {dep: ctx.inputs[dep].output for dep in self.spec.depends_on}


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def test_registry() -> NodeRegistry:
    """A fresh registry per test so registrations don't leak across tests."""
    reg = NodeRegistry()
    reg.register("test.echo", EchoNode)
    reg.register("test.fail_once", FailOnceNode)
    reg.register("test.boom", BoomNode)
    reg.register("test.slow", SlowNode)
    reg.register("test.collect", CollectInputsNode)
    return reg


@pytest.fixture(autouse=True)
def _reset_fail_counts():
    FailOnceNode._attempt_counts.clear()


@pytest.fixture
def make_execution():
    """Factory: build an ExecutionContext with an EventBus + run_id."""
    def _make(query: str = "test query", user_context: dict | None = None,
              heartbeat_s: float = 60.0, queue_size: int = 256) -> ExecutionContext:
        run_id = uuid.uuid4().hex
        bus = EventBus(run_id=run_id, maxsize=queue_size, heartbeat_interval_s=heartbeat_s)
        return ExecutionContext(
            workflow_id="test",
            run_id=run_id,
            query=query,
            user_context=user_context or {},
            events=bus,
        )
    return _make


@pytest.fixture
def make_scheduler(test_registry):
    def _make() -> Scheduler:
        return Scheduler(registry=test_registry)
    return _make


@pytest.fixture
def collect_events():
    """Helper: drain the EventBus into a list. Caller closes the bus to terminate."""
    async def _collect(bus: EventBus) -> List:
        out = []
        async for ev in bus.stream():
            out.append(ev)
        return out
    return _collect
