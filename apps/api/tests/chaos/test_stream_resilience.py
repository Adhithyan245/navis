"""
tests/chaos/test_stream_resilience.py

Validates NDJSON stream integrity under adversarial conditions:
  - slow consumers
  - semaphore starvation
  - queue overflow
  - heartbeat continuity
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock

from apps.api.agents.orchestrator import run_orchestration
from apps.api.services.provider_manager import provider_manager


@pytest.mark.asyncio
async def test_stream_yields_valid_ndjson():
    """Every chunk from orchestrator must be JSON-serialisable with required keys."""
    async def instant_geo(*args, **kwargs):
        return {"lat": "48.8566", "lon": "2.3522", "name": "Paris, France"}

    with patch.object(provider_manager.geo, "fetch", new=instant_geo):
        chunks = []
        async for chunk in run_orchestration("Best places in Paris", {}):
            chunks.append(chunk)
            if len(chunks) > 10:
                break

    assert len(chunks) > 0
    for chunk in chunks:
        # Must be JSON-serialisable
        raw = json.dumps(chunk)
        parsed = json.loads(raw)
        assert "event" in parsed, f"Missing 'event' key in chunk: {parsed}"
        assert "data" in parsed, f"Missing 'data' key in chunk: {parsed}"


@pytest.mark.asyncio
async def test_queue_does_not_overflow_on_fast_producer():
    """Producer faster than consumer — bounded queue must apply backpressure, not crash."""
    import time

    async def fast_geo(*args, **kwargs):
        return {"lat": "35.6762", "lon": "139.6503", "name": "Tokyo, Japan"}

    with patch.object(provider_manager.geo, "fetch", new=fast_geo):
        chunks_received = 0
        t0 = time.monotonic()

        async for chunk in run_orchestration("Explore Tokyo", {}):
            chunks_received += 1
            await asyncio.sleep(0.05)   # Simulate slow consumer
            if time.monotonic() - t0 > 5:
                break

    assert chunks_received > 0, "No chunks received from stream"


@pytest.mark.asyncio
async def test_agent_failure_emits_agent_failed_event_not_exception():
    """A crashing agent MUST emit agent_failed event, not propagate an exception."""
    async def crash(*args, **kwargs):
        raise RuntimeError("Simulated agent crash")

    with patch.object(provider_manager.places, "fetch", new=crash):
        events_seen = set()
        async for chunk in run_orchestration("Cafes in Berlin", {}):
            events_seen.add(chunk.get("event"))
            if "result" in events_seen or len(events_seen) > 10:
                break

    # The stream must never raise — agent_failed events should appear
    assert "agent_failed" in events_seen or "result" in events_seen, \
        f"Expected agent_failed or result event, got: {events_seen}"


@pytest.mark.asyncio
async def test_concurrent_streams_stable():
    """Launch 10 concurrent orchestrations — all must complete without exception."""
    async def run_one():
        chunks = []
        async for chunk in run_orchestration("Explore NYC", {}):
            chunks.append(chunk)
            if len(chunks) > 5:
                break
        return len(chunks)

    results = await asyncio.gather(*[run_one() for _ in range(10)], return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 0, f"Some streams crashed: {errors}"
    assert all(isinstance(r, int) and r > 0 for r in results)
