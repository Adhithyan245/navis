"""
Wire view translator — the only place internal runtime events become
user-facing NDJSON.

The runtime emits a rich stream of operational events: workflow_started,
node_started, node_completed, node_failed, provider_fallback, etc. Those
events are essential for observability and tracing but MUST NEVER reach
the client. The Navis UX principle is "invisible orchestration": the user
sees results refining themselves, never the machinery doing the refining.

This module exposes one function, `external_stream`, that subscribes to an
internal EventBus and yields NDJSON lines for *only* the events that
represent meaningful product output. Everything else is funnelled to the
structured logger.

Allowlist (user-facing):
  * partial_result   — progressive recommendations during a run
  * final_result     — assembled, humanized output
  * stream_heartbeat — transport keepalive
  * error            — scrubbed terminal error (no internals)

Everything else is internal-only.
"""
from __future__ import annotations

from typing import AsyncIterator, Set

import orjson

from apps.api.core.logging import get_logger
from apps.api.runtime.events import Event, EventBus, EventType

logger = get_logger(__name__)


USER_FACING_EVENTS: Set[EventType] = {
    EventType.PARTIAL_RESULT,
    EventType.FINAL_RESULT,
    EventType.STREAM_HEARTBEAT,
}

# Events that terminate the wire with a scrubbed error message.
TERMINAL_FAILURE_EVENTS: Set[EventType] = {
    EventType.WORKFLOW_FAILED,
}

# Generic message returned to clients on any internal failure. We never
# surface node ids, exception types, or stack traces.
_GENERIC_ERROR = {
    "message": "We couldn't complete that request. Please try again.",
}


def _encode_user_event(event_name: str, data) -> bytes:
    # Intentionally minimal shape: only `event` + `data`. No timestamps, no
    # run_ids, no internal metadata. Keeps the wire surface tight.
    return orjson.dumps({"event": event_name, "data": data}) + b"\n"


async def external_stream(bus: EventBus) -> AsyncIterator[bytes]:
    """
    Subscribe to an internal EventBus and yield NDJSON only for events the
    client is allowed to see. Internal events go to the structured logger.

    Cancellation propagates back into bus.stream() naturally.
    """
    async for event in bus.stream():
        try:
            if event.type in USER_FACING_EVENTS:
                yield _encode_user_event(event.type.value, event.data)
                continue

            if event.type in TERMINAL_FAILURE_EVENTS:
                logger.error(
                    "runtime.event.terminal_failure",
                    run_id=event.run_id,
                    event_type=event.type.value,
                    detail=event.data,
                )
                yield _encode_user_event("error", _GENERIC_ERROR)
                continue

            # Internal-only — log for tracing, do not emit.
            logger.info(
                "runtime.event",
                run_id=event.run_id,
                event_type=event.type.value,
                data=event.data,
            )
        except Exception as exc:
            # Translator failures must never poison the stream; log and continue.
            logger.error(
                "runtime.view.translator_error",
                run_id=event.run_id,
                event_type=event.type.value,
                error=str(exc),
            )
