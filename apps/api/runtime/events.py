"""
EventBus — bounded, cancellation-safe async event pipeline.

Producers (Scheduler, Nodes) call `await bus.emit(type, data)`. A single
consumer (the HTTP streaming route) iterates `async for event in bus.stream()`
and writes each event as one NDJSON line.

Design choices
--------------
* **Bounded queue** for backpressure. If a downstream consumer stalls, the
  queue fills and producers block (or drop, see `BackpressurePolicy`).
* **Single consumer.** This bus is per-workflow-run, sized to its own HTTP
  stream. Multi-consumer fan-out would need a Topic abstraction — not in
  scope. Calling `stream()` twice on the same bus is undefined.
* **Heartbeats**: a separate watchdog task emits STREAM_HEARTBEAT every
  `heartbeat_interval_s` if nothing else was emitted recently. Watchdog is
  started by `start()` and stopped by `close()`.
* **NDJSON via orjson.** Serialisation lives next to the bus so the route
  layer never touches event internals.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, Optional

import orjson

from apps.api.core.logging import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    """Wire-stable event type identifiers. Never renumber — only add."""
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_FAILED = "workflow_failed"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_SKIPPED = "node_skipped"
    NODE_PARTIAL = "node_partial"           # mid-execution incremental data
    PROVIDER_FALLBACK = "provider_fallback"
    STREAM_HEARTBEAT = "stream_heartbeat"
    PARTIAL_RESULT = "partial_result"
    FINAL_RESULT = "final_result"


class BackpressurePolicy(str, Enum):
    BLOCK = "block"       # default — producer waits for queue space
    DROP_OLDEST = "drop_oldest"
    DROP_NEW = "drop_new"


@dataclass
class Event:
    type: EventType
    data: Any
    ts: float = field(default_factory=lambda: time.time())
    run_id: Optional[str] = None

    def to_ndjson(self) -> bytes:
        payload: Dict[str, Any] = {
            "event": self.type.value,
            "data": self.data,
            "ts": self.ts,
        }
        if self.run_id:
            payload["run_id"] = self.run_id
        return orjson.dumps(payload) + b"\n"


class EventBus:
    def __init__(
        self,
        run_id: str,
        *,
        maxsize: int = 256,
        heartbeat_interval_s: float = 5.0,
        backpressure: BackpressurePolicy = BackpressurePolicy.BLOCK,
    ) -> None:
        self.run_id = run_id
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._heartbeat_interval = heartbeat_interval_s
        self._backpressure = backpressure
        self._last_emit_at = time.monotonic()
        self._closed = False
        self._done: asyncio.Event = asyncio.Event()
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ── producer side ─────────────────────────────────────────────────────

    async def emit(self, event_type: EventType, data: Any) -> None:
        """Emit an event. Honours the configured backpressure policy."""
        if self._closed:
            return
        ev = Event(type=event_type, data=data, run_id=self.run_id)
        self._last_emit_at = time.monotonic()

        if self._backpressure is BackpressurePolicy.BLOCK:
            await self._queue.put(ev)
            return

        try:
            self._queue.put_nowait(ev)
        except asyncio.QueueFull:
            if self._backpressure is BackpressurePolicy.DROP_NEW:
                logger.warning("event_bus.drop_new", run_id=self.run_id, type=event_type.value)
                return
            # DROP_OLDEST
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(ev)
            except asyncio.QueueFull:
                logger.warning("event_bus.drop_after_evict", run_id=self.run_id)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spin up the heartbeat watchdog."""
        if self._heartbeat_task is None and self._heartbeat_interval > 0:
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name=f"event-bus-heartbeat:{self.run_id}",
            )

    async def close(self) -> None:
        """Stop watchdog and signal end-of-stream to consumers."""
        if self._closed:
            return
        self._closed = True
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            self._heartbeat_task = None
        # Signal end-of-stream. The stream() coroutine drains any queued
        # events then terminates. No in-queue sentinel needed, so close()
        # works regardless of backpressure policy and never deadlocks on
        # a full queue.
        self._done.set()

    # ── consumer side ─────────────────────────────────────────────────────

    async def stream(self) -> AsyncIterator[Event]:
        """
        Single-consumer async iterator. Ends after close() is called AND
        any remaining queued events have been drained.

        Cancellation-safe: if the caller's task is cancelled, the iterator
        exits cleanly without leaving items in flight.
        """
        done_wait: Optional[asyncio.Task] = None
        try:
            while True:
                # Fast path: already-buffered events drain without an extra await
                try:
                    yield self._queue.get_nowait()
                    continue
                except asyncio.QueueEmpty:
                    pass

                if self._done.is_set():
                    return

                if done_wait is None or done_wait.done():
                    done_wait = asyncio.create_task(self._done.wait())
                get_task = asyncio.create_task(self._queue.get())
                done_set, _ = await asyncio.wait(
                    {get_task, done_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if get_task in done_set:
                    yield get_task.result()
                else:
                    get_task.cancel()
                    # Loop around — done is set; the fast path will drain
                    # any straggling events before we exit.
        except asyncio.CancelledError:
            raise
        finally:
            if done_wait is not None and not done_wait.done():
                done_wait.cancel()

    # ── internal ──────────────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self._heartbeat_interval)
                if self._closed:
                    return
                idle_s = time.monotonic() - self._last_emit_at
                if idle_s >= self._heartbeat_interval:
                    await self.emit(
                        EventType.STREAM_HEARTBEAT,
                        {"idle_s": round(idle_s, 2)},
                    )
        except asyncio.CancelledError:
            return
