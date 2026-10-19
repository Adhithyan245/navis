"""
Slow-consumer / backpressure tests.

When a downstream consumer is slow, the EventBus's bounded queue must
apply backpressure (block producers) without deadlocking or losing events
that fit within the queue. With BLOCK policy + a tight queue, producers
wait for the consumer to catch up.
"""
from __future__ import annotations

import asyncio

import pytest

from apps.api.runtime.events import BackpressurePolicy, EventBus, EventType


@pytest.mark.asyncio
async def test_backpressure_block_does_not_lose_events():
    bus = EventBus(
        run_id="t", maxsize=4, heartbeat_interval_s=60.0,
        backpressure=BackpressurePolicy.BLOCK,
    )

    async def slow_consumer():
        received = []
        async for ev in bus.stream():
            received.append(ev)
            await asyncio.sleep(0.005)
        return received

    consumer_task = asyncio.create_task(slow_consumer())

    # Fire more events than the queue can hold — backpressure should block,
    # not drop.
    for i in range(20):
        await bus.emit(EventType.PARTIAL_RESULT, {"i": i})
    await bus.close()

    received = await consumer_task
    indices = [e.data["i"] for e in received if e.type == EventType.PARTIAL_RESULT]
    assert indices == list(range(20)), f"events lost or reordered: {indices}"


@pytest.mark.asyncio
async def test_drop_oldest_keeps_newest():
    bus = EventBus(
        run_id="t", maxsize=2, heartbeat_interval_s=60.0,
        backpressure=BackpressurePolicy.DROP_OLDEST,
    )

    # Fill + overflow before any consumer reads
    await bus.emit(EventType.PARTIAL_RESULT, {"i": 0})
    await bus.emit(EventType.PARTIAL_RESULT, {"i": 1})
    await bus.emit(EventType.PARTIAL_RESULT, {"i": 2})
    await bus.emit(EventType.PARTIAL_RESULT, {"i": 3})
    await bus.close()

    received = []
    async for ev in bus.stream():
        received.append(ev)

    indices = [e.data["i"] for e in received if e.type == EventType.PARTIAL_RESULT]
    # Oldest dropped, newest retained
    assert 3 in indices
    assert 0 not in indices


@pytest.mark.asyncio
async def test_drop_new_when_full():
    bus = EventBus(
        run_id="t", maxsize=2, heartbeat_interval_s=60.0,
        backpressure=BackpressurePolicy.DROP_NEW,
    )

    await bus.emit(EventType.PARTIAL_RESULT, {"i": 0})
    await bus.emit(EventType.PARTIAL_RESULT, {"i": 1})
    await bus.emit(EventType.PARTIAL_RESULT, {"i": 2})  # should be dropped
    await bus.emit(EventType.PARTIAL_RESULT, {"i": 3})  # should be dropped
    await bus.close()

    received = []
    async for ev in bus.stream():
        received.append(ev)

    indices = [e.data["i"] for e in received if e.type == EventType.PARTIAL_RESULT]
    assert indices == [0, 1]
