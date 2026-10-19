from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/saved", tags=["saved"])

@router.post("/items")
async def list_saved(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_saved(context, trace=trace),
        media_type="application/x-ndjson"
    )
