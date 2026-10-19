from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/explore", tags=["explore"])

@router.post("/search")
async def explore_city(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_explore(context, trace=trace),
        media_type="application/x-ndjson"
    )
