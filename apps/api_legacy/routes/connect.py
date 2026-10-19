from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/connect", tags=["connect"])

@router.post("/events")
async def local_events(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_events(context, trace=trace),
        media_type="application/x-ndjson"
    )
