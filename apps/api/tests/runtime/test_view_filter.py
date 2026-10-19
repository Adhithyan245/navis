"""
View filter: the external stream MUST NOT leak internal runtime events to
clients. Only user-facing events (partial_result, final_result, heartbeat,
error) cross the wire.

This is the test that enforces Navis's "invisible orchestration" UX rule.
"""
from __future__ import annotations

import asyncio

import orjson
import pytest

from apps.api.runtime.events import EventBus, EventType
from apps.api.runtime.view import USER_FACING_EVENTS, external_stream


_USER_FACING_NAMES = {e.value for e in USER_FACING_EVENTS} | {"error"}
_INTERNAL_NAMES = {
    "workflow_started", "workflow_completed", "workflow_cancelled",
    "node_started", "node_completed", "node_failed", "node_skipped",
    "node_partial", "provider_fallback",
}


@pytest.mark.asyncio
async def test_internal_events_never_cross_wire():
    bus = EventBus(run_id="t", maxsize=64, heartbeat_interval_s=60.0)

    # Emit a representative slice of internal + user-facing events
    await bus.emit(EventType.WORKFLOW_STARTED, {"workflow": "x"})
    await bus.emit(EventType.NODE_STARTED, {"node_id": "geo"})
    await bus.emit(EventType.NODE_COMPLETED, {"node_id": "geo"})
    await bus.emit(EventType.PROVIDER_FALLBACK, {"provider": "places"})
    await bus.emit(EventType.PARTIAL_RESULT, {"items": [1, 2]})
    await bus.emit(EventType.FINAL_RESULT, {"summary": "hi"})
    await bus.emit(EventType.WORKFLOW_COMPLETED, {"workflow": "x"})
    await bus.close()

    lines = []
    async for line in external_stream(bus):
        lines.append(orjson.loads(line))

    seen_events = {l["event"] for l in lines}

    # Every internal event type must be filtered out
    leaked = seen_events & _INTERNAL_NAMES
    assert not leaked, f"internal events leaked to wire: {leaked}"

    # Only user-facing events come through
    assert seen_events == {"partial_result", "final_result"}


@pytest.mark.asyncio
async def test_workflow_failed_becomes_scrubbed_error():
    bus = EventBus(run_id="t", heartbeat_interval_s=60.0)
    await bus.emit(EventType.WORKFLOW_FAILED, {
        "error": "RuntimeError: secret internal detail",
        "node_id": "places_search",
    })
    await bus.close()

    lines = []
    async for line in external_stream(bus):
        lines.append(orjson.loads(line))

    assert len(lines) == 1
    assert lines[0]["event"] == "error"
    # Generic message only — no internal node ids or exception names
    payload_str = orjson.dumps(lines[0]["data"]).decode()
    assert "RuntimeError" not in payload_str
    assert "places_search" not in payload_str
    assert "secret internal detail" not in payload_str


@pytest.mark.asyncio
async def test_user_event_payload_has_no_run_id_or_ts():
    """Wire shape stays minimal — no run_id, no ts, just event + data."""
    bus = EventBus(run_id="t", heartbeat_interval_s=60.0)
    await bus.emit(EventType.FINAL_RESULT, {"x": 1})
    await bus.close()

    async for line in external_stream(bus):
        parsed = orjson.loads(line)
        assert set(parsed.keys()) == {"event", "data"}
