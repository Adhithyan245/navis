"""
Voice / Ask Native agent route — intent parsing and multi-agent routing.

POST /voice/query

GUARANTEE: This endpoint NEVER returns 500.
Any uncaught exception produces a graceful NDJSON fallback stream.
"""

import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)
_orchestrator = OrchestratorAgent()


class VoiceQueryRequest(BaseModel):
    context: Optional[UserContext] = None
    transcript: str = ""


async def _safe_stream(context: UserContext, transcript: str, trace: bool = False):
    """
    Wraps the orchestrator stream in a top-level exception guard.
    If the entire orchestrator crashes, emits a safe terminal NDJSON event.
    Individual yield failures within the stream are also caught.
    """
    try:
        async for chunk in _orchestrator.stream_voice_query(context, transcript, trace=trace):
            try:
                yield chunk
            except Exception as e:
                logger.error("voice: failed to yield chunk: %s", e)
                continue
    except Exception as e:
        logger.error("voice: orchestrator stream crashed: %s", e)
        # Emit a safe terminal event so the client always gets a complete response
        fallback_event = {
            "state": "completed",
            "progress": 100,
            "data": {
                "status": "error",
                "data": {"results": []},
                "message": "An internal error occurred. Please try again.",
                "explanation": str(e),
                "context_used": {},
                "sources": [],
                "source_mode": "fallback",
            }
        }
        yield json.dumps(fallback_event) + "\n"


@router.post("/query")
async def voice_query(request: VoiceQueryRequest, trace: bool = False):
    """
    Parse a natural language transcript and route to the correct agent.

    When OPENAI_API_KEY is configured, uses GPT-4o-mini for intent detection.
    Falls back to keyword-based routing when OpenAI is unavailable — always
    returns a usable response.

    Returns a streaming NDJSON response with:
    - Parsed intent (agent, confidence, method)
    - The routed agent's response embedded in data
    """
    # Ensure context is never None
    context = request.context or UserContext()
    transcript = request.transcript or ""
    
    return StreamingResponse(
        _safe_stream(context, transcript, trace=trace),
        media_type="application/x-ndjson",
    )
