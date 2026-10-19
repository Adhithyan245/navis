"""
Transit agent route — live public transit data.

POST /transit/info
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/transit", tags=["transit"])
_orchestrator = OrchestratorAgent()


@router.post("/info")
async def transit_info(context: UserContext, trace: bool = False):
    """
    Fetch live public transit data for the user's destination city.

    Currently supported cities: Boston (MBTA — live routes and alerts).
    Cities without a registered provider return a structured fallback
    with capability notes.

    Returns a streaming NDJSON response with routes, stops, and alerts.
    """
    return StreamingResponse(
        _orchestrator.stream_transit(context, trace=trace),
        media_type="application/x-ndjson",
    )
