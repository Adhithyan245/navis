"""
Taste agent route — food discovery powered by Google Places + optional Yelp.

POST /taste/discover
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/taste", tags=["taste"])
_orchestrator = OrchestratorAgent()


@router.post("/discover")
async def taste_discover(context: UserContext, trace: bool = False):
    """
    Discover food spots — restaurants, cafes, and local cuisine.

    Uses the user's food_preferences and preferences fields to build a
    targeted query. Google Places is the primary source; Yelp enriches
    results when YELP_API_KEY is configured.

    Returns a streaming NDJSON response of agent events.
    """
    return StreamingResponse(
        _orchestrator.stream_taste(context, trace=trace),
        media_type="application/x-ndjson",
    )
