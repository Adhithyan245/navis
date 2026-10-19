"""
POST /v2/query

Single entry point for the multi-agent layer: the supervisor
(apps/api/agentic/supervisor.py) routes the query to agents, runs them
(workflow-backed ones as one composed runtime graph) and streams a unified
NDJSON response.

Like `/v2/workflow/{name}`, the wire surface is the same minimal set —
`partial_result`, `final_result`, `stream_heartbeat`, scrubbed `error`.
The route layer is intentionally thin; everything else lives in the
runtime modules.
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Dict, Optional

import orjson
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.api.core.logging import get_logger
from apps.api.agentic.supervisor import run_agents_ndjson

logger = get_logger(__name__)
router = APIRouter(prefix="/v2")


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/query")
async def query(payload: QueryRequest, req: Request) -> StreamingResponse:
    async def generate() -> AsyncIterator[bytes]:
        max_duration_s = 120.0
        start = time.monotonic()

        try:
            async for line in run_agents_ndjson(
                payload.query,
                payload.user_context or {},
                metadata=payload.metadata or {},
            ):
                if await req.is_disconnected():
                    logger.info("client disconnected mid-stream", route="/v2/query")
                    break
                if time.monotonic() - start > max_duration_s:
                    yield orjson.dumps({
                        "event": "error",
                        "data": {"message": "Request took too long. Please try again."},
                    }) + b"\n"
                    break
                yield line
        except Exception as exc:
            logger.error("query stream error", error=str(exc))
            yield orjson.dumps({
                "event": "error",
                "data": {"message": "We couldn't complete that request. Please try again."},
            }) + b"\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
