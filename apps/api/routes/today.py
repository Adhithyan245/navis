"""
POST /v2/today — the newcomer hub for the user's place: weather, what's on
tonight, tech & community, getting around, getting here, money, safety and
local know-how, each from its own agent, streamed as sections.

Same wire contract as /v2/query (partial_result / final_result /
stream_heartbeat / error).
"""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Dict, Optional

import orjson
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apps.api.agentic.supervisor import run_agents_ndjson
from apps.api.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v2")

HUB_AGENTS = ["weather", "live_events", "tech_community", "transit", "arrival", "money",
              "safety_health", "local_knowledge"]


class TodayRequest(BaseModel):
    user_context: Optional[Dict[str, Any]] = None


@router.post("/today")
async def today(payload: TodayRequest, req: Request) -> StreamingResponse:
    ctx = payload.user_context or {}
    city = ctx.get("city") if isinstance(ctx.get("city"), str) else ""
    # Workflow-backed agents (live events) read the query text.
    query = f"events in {city} today" if city else "events today"

    async def generate() -> AsyncIterator[bytes]:
        start = time.monotonic()
        try:
            async for line in run_agents_ndjson(
                query, ctx, agents=HUB_AGENTS,
                # The tech card looks two weeks ahead; "what's on" stays today.
                metadata={"agent_options": {"window_days": 14}},
            ):
                if await req.is_disconnected():
                    break
                if time.monotonic() - start > 120:
                    yield orjson.dumps({"event": "error", "data": {"message": "Request took too long. Please try again."}}) + b"\n"
                    break
                yield line
        except Exception as exc:  # noqa: BLE001
            logger.error("today stream error", error=str(exc))
            yield orjson.dumps({"event": "error", "data": {"message": "We couldn't complete that request. Please try again."}}) + b"\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
