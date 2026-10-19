from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/move", tags=["move"])

@router.post("/transit")
async def mobility(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_move(context, trace=trace),
        media_type="application/x-ndjson"
    )
