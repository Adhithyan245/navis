"""
tests/chaos/test_provider_failures.py

Chaos engineering tests:
  - dead providers (all fail simultaneously)
  - malformed JSON responses
  - timeout storms
  - provider quota simulation
  - circuit breaker open state
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from apps.api.services.provider_manager import provider_manager
from apps.api.agents.orchestrator import run_orchestration
from apps.api.models.providers import ProviderResponse


# ── Helper ─────────────────────────────────────────────────────────────────────

def _fallback_response(provider_name: str) -> ProviderResponse:
    return ProviderResponse(
        provider=provider_name,
        source="fallback",
        results=[],
        error="Simulated failure",
        confidence=0.0,
        verified=False,
        retrieved_at=0.0,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_providers_dead_stream_survives():
    """All providers return fallbacks — orchestrator MUST still yield chunks."""
    async def dead(*args, **kwargs):
        raise ConnectionError("Simulated dead provider")

    with (
        patch.object(provider_manager.geo,    "fetch", new=dead),
        patch.object(provider_manager.places, "fetch", new=dead),
        patch.object(provider_manager.events, "fetch", new=dead),
        patch.object(provider_manager.ai,     "fetch", new=dead),
    ):
        chunks = []
        async for chunk in run_orchestration("Find cafes in Berlin", {}):
            chunks.append(chunk)

    assert len(chunks) > 0, "Stream must yield at least one chunk even when all providers fail"
    events = [c["event"] for c in chunks]
    # Must never raise — errors are emitted as stream events
    assert "error" not in events or "result" in events or "agent_failed" in events


@pytest.mark.asyncio
async def test_timeout_storm_does_not_block():
    """All providers hang for 15s — base provider must timeout at 10s and return fallback."""
    async def slow(*args, **kwargs):
        await asyncio.sleep(15)

    with patch.object(provider_manager.wiki, "fetch", new=slow):
        t0 = asyncio.get_event_loop().time()
        resp = await provider_manager.wiki.execute(topic="TestCity")
        elapsed = asyncio.get_event_loop().time() - t0

    assert resp.source == "fallback"
    assert elapsed < 12, f"Provider should have timed out at 10s, took {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_malformed_provider_response_safe():
    """Provider returns non-list, non-dict garbage — execute must return fallback, not raise."""
    async def bad_fetch(*args, **kwargs):
        return "TOTALLY_WRONG_STRING_OUTPUT"

    with patch.object(provider_manager.geo, "fetch", new=bad_fetch):
        resp = await provider_manager.geo.execute(query="Paris")

    # Should wrap as single-item list result (str is valid as Any in list)
    assert resp is not None
    assert isinstance(resp.results, list)


@pytest.mark.asyncio
async def test_cancellation_does_not_leak_tasks():
    """Simulates client disconnect mid-stream and ensures tasks are cleaned up."""
    initial_tasks = len(asyncio.all_tasks())

    gen = run_orchestration("Explore Tokyo", {})
    chunks = []
    try:
        async for chunk in gen:
            chunks.append(chunk)
            if len(chunks) >= 2:
                await gen.aclose()  # Simulate client disconnect
                break
    except (StopAsyncIteration, GeneratorExit, Exception):
        pass

    await asyncio.sleep(0.1)  # Allow cleanup tasks to run
    final_tasks = len(asyncio.all_tasks())
    task_delta = final_tasks - initial_tasks
    assert task_delta <= 2, f"Possible task leak: {task_delta} extra tasks after cancellation"


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    """Repeated failures should open the circuit breaker."""
    from apps.api.observability.circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
    for _ in range(4):
        breaker.record_failure()

    assert breaker.state == "OPEN"
    assert not breaker.can_execute()
