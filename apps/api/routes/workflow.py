"""
POST /v2/workflow/{name}

Executes a registered workflow against the runtime engine and streams the
event pipeline back as NDJSON. The route is intentionally thin — all
streaming, cancellation, and event encoding lives in the runtime layer.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Dict, Optional

import orjson
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.api.core.logging import get_logger
from apps.api.runtime.compiler.registry import WorkflowNotFound, workflow_registry
from apps.api.runtime.runner import run_workflow_ndjson

logger = get_logger(__name__)
router = APIRouter(prefix="/v2/workflow")


class WorkflowRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("")
async def list_workflows() -> Dict[str, Any]:
    return {"workflows": list(workflow_registry.names())}


@router.post("/{name}")
async def run_workflow(name: str, payload: WorkflowRequest, req: Request) -> StreamingResponse:
    try:
        workflow_registry.get(name)
    except WorkflowNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    async def generate() -> AsyncIterator[bytes]:
        # Stream-abort watchdog: if the client disconnects, stop pulling
        # from the runtime promptly. The runner handles the actual teardown
        # via task cancellation.
        max_duration_s = 120.0
        start = time.monotonic()

        try:
            async for line in run_workflow_ndjson(
                name,
                payload.query,
                payload.user_context or {},
                metadata=payload.metadata or {},
            ):
                if await req.is_disconnected():
                    logger.info("client disconnected mid-stream", workflow=name)
                    break
                if time.monotonic() - start > max_duration_s:
                    yield orjson.dumps({
                        "event": "error",
                        "data": {"message": "Request took too long. Please try again."},
                    }) + b"\n"
                    break
                yield line
        except Exception as exc:
            logger.error("workflow stream error", workflow=name, error=str(exc))
            # Only the scrubbed error crosses the wire — never exception text.
            yield orjson.dumps({
                "event": "error",
                "data": {"message": "We couldn't complete that request. Please try again."},
            }) + b"\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
