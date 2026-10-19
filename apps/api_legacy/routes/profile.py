from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/profile", tags=["profile"])

@router.post("/me")
async def user_profile(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_profile(context, trace=trace),
        media_type="application/x-ndjson"
    )
