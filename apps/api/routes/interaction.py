import asyncio
import orjson
import time
import logging
from typing import List, Optional, Any
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from apps.api.models.responses import InteractionRequest, APIResponse
from apps.api.agents.orchestrator import run_orchestration
from apps.api.services.behavior import behavior_tracker
from apps.api.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

class InteractionPayload(BaseModel):
    user_id: str
    item_id: str
    item_type: str                        # "place" | "event" | "service"
    domain: str                           # "explore" | "connect" | "services" | "work" | "move"
    categories: Optional[List[str]] = None

def safe_user_id(raw: Any) -> int:
    """Parse user_id safely — NEVER throws."""
    if not raw:
        return -1
    try:
        s = str(raw).strip()
        return int(s) if s.isdigit() else -1
    except Exception:
        return -1

# Wire contract (invisible orchestration): only these events may reach the
# client. Orchestrator chatter (status, context_updated, agent_success,
# agent_failed, ...) is logged and dropped at this boundary.
_GENERIC_ERROR = {"message": "We couldn't complete that request. Please try again."}
_TIMEOUT_ERROR = {"message": "Request took too long. Please try again."}


def to_wire_event(chunk: Any) -> Optional[dict]:
    """Translate an internal orchestration chunk into a client-facing event,
    or None when the chunk is internal-only. Never forwards exception text."""
    if not isinstance(chunk, dict):
        return None
    event = chunk.get("event")
    if event in ("heartbeat", "stream_heartbeat"):
        return {"event": "stream_heartbeat", "data": {}}
    if event in ("result", "final_result"):
        data = chunk.get("data") if isinstance(chunk.get("data"), dict) else {}
        return {
            "event": "final_result",
            "data": {
                "response": data.get("response", ""),
                "result_count": data.get("raw_data_count", data.get("result_count", 0)),
            },
        }
    if event == "error":
        return {"event": "error", "data": _GENERIC_ERROR}
    logger.info("interact.internal_event", event_type=event)
    return None


async def heartbeat_watchdog(queue: asyncio.Queue, cancel_event: asyncio.Event):
    """Injects heartbeats into the queue periodically if no data is sent."""
    while not cancel_event.is_set():
        try:
            await asyncio.sleep(5)
            if not cancel_event.is_set():
                await queue.put({"event": "heartbeat", "data": "alive", "timestamp": time.time()})
        except asyncio.CancelledError:
            break

async def orchestration_producer(request: InteractionRequest, context: dict, queue: asyncio.Queue, cancel_event: asyncio.Event):
    """Runs orchestration and pushes results to a queue."""
    try:
        async for chunk in run_orchestration(request.query, context):
            if cancel_event.is_set():
                break
            await queue.put(chunk)
    except asyncio.CancelledError:
        logger.warning("Orchestration producer cancelled")
    except Exception as e:
        logger.error(f"Orchestration fatal error: {e}")
        await queue.put({"event": "error", "data": _GENERIC_ERROR})
    finally:
        await queue.put(None)  # EOF marker

@router.post("/interact")
async def interact(request: InteractionRequest, req: Request):
    """
    Main entry point for Navis orchestration.
    Streams NDJSON responses back to the client with strict safety.
    """
    queue = asyncio.Queue(maxsize=100) # Backpressure queue
    cancel_event = asyncio.Event()
    
    async def generate():
        watchdog_task = asyncio.create_task(heartbeat_watchdog(queue, cancel_event))
        producer_task = asyncio.create_task(orchestration_producer(request, request.context or {}, queue, cancel_event))
        
        start_time = time.time()
        max_duration = 60.0  # Max stream duration
        
        try:
            yield orjson.dumps({"event": "stream_heartbeat", "data": {}}) + b"\n"
            
            while True:
                # Disconnect check
                if await req.is_disconnected():
                    logger.info("Client disconnected, cancelling stream.")
                    break
                    
                # Timeout check
                if time.time() - start_time > max_duration:
                    logger.warning("Stream max duration reached.")
                    yield orjson.dumps({"event": "error", "data": _TIMEOUT_ERROR}) + b"\n"
                    break
                    
                try:
                    # Wait for next item from queue, with short timeout to allow disconnect checks
                    chunk = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    if chunk is None:  # EOF
                        break

                    wire = to_wire_event(chunk)
                    if wire is None:
                        continue

                    # Measure yield time for slow-consumer protection
                    yield_start = time.time()
                    yield orjson.dumps(wire) + b"\n"
                    
                    if time.time() - yield_start > 2.0:
                        logger.warning("Slow consumer detected, aborting stream")
                        break
                except asyncio.TimeoutError:
                    continue # Loop around to check disconnects
                    
        except asyncio.CancelledError:
            logger.info("Streaming response cancelled by ASGI server")
            raise
        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            yield orjson.dumps({"event": "error", "data": _GENERIC_ERROR}) + b"\n"
        finally:
            # Cleanup
            cancel_event.set()
            watchdog_task.cancel()
            producer_task.cancel()
            # Wait briefly for tasks to clean up
            await asyncio.gather(watchdog_task, producer_task, return_exceptions=True)
            logger.info("Stream resources cleaned up")

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/interaction/click")
async def log_click(payload: InteractionPayload):
    """Log a real user click on a result item."""
    try:
        uid = safe_user_id(payload.user_id)
        if uid > 0:
            behavior_tracker.record_click(
                uid,
                payload.item_id,
                payload.item_type,
                payload.domain,
                payload.categories or [],
            )
    except Exception as exc:
        logger.error("interaction/click log failed: %s", exc)
        
    return {
        "status": "success",
        "agent": "interaction",
        "source": "user_profiles_db",
        "data": {"message": "interaction recorded"},
        "explanation": "User interaction logged successfully.",
        "context_used": {"user_id": payload.user_id},
        "sources": ["user_profiles_db"],
        "source_mode": "mixed"
    }


@router.post("/interaction/save")
async def log_save(payload: InteractionPayload):
    """Log a real user save action on a result item."""
    try:
        uid = safe_user_id(payload.user_id)
        if uid > 0:
            behavior_tracker.record_save(
                uid,
                payload.item_id,
                payload.item_type,
                payload.domain,
                payload.categories or [],
            )
    except Exception as exc:
        logger.error("interaction/save log failed: %s", exc)
        
    return {
        "status": "success",
        "agent": "interaction",
        "source": "user_profiles_db",
        "data": {"message": "interaction recorded"},
        "explanation": "User interaction logged successfully.",
        "context_used": {"user_id": payload.user_id},
        "sources": ["user_profiles_db"],
        "source_mode": "mixed"
    }


@router.post("/interaction/ignore")
async def log_ignore(payload: InteractionPayload):
    """Log a negative user avoid/ignore signal on a result item."""
    try:
        uid = safe_user_id(payload.user_id)
        if uid > 0:
            behavior_tracker.record_ignore(
                uid,
                payload.item_id,
                payload.item_type,
                payload.domain,
                payload.categories or [],
            )
    except Exception as exc:
        logger.error("interaction/ignore log failed: %s", exc)
        
    return {
        "status": "success",
        "agent": "interaction",
        "source": "user_profiles_db",
        "data": {"message": "interaction recorded"},
        "explanation": "User interaction logged successfully.",
        "context_used": {"user_id": payload.user_id},
        "sources": ["user_profiles_db"],
        "source_mode": "mixed"
    }


@router.post("/interaction/dismiss")
async def log_dismiss(payload: InteractionPayload):
    """Log a negative user dismissal signal on a result item."""
    try:
        uid = safe_user_id(payload.user_id)
        if uid > 0:
            behavior_tracker.record_dismiss(
                uid,
                payload.item_id,
                payload.item_type,
                payload.domain,
                payload.categories or [],
            )
    except Exception as exc:
        logger.error("interaction/dismiss log failed: %s", exc)
        
    return {
        "status": "success",
        "agent": "interaction",
        "source": "user_profiles_db",
        "data": {"message": "interaction recorded"},
        "explanation": "User interaction logged successfully.",
        "context_used": {"user_id": payload.user_id},
        "sources": ["user_profiles_db"],
        "source_mode": "mixed"
    }
