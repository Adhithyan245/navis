from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/home", tags=["home"])

@router.post("/aggregate")
async def home_dashboard(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_home(context, trace=trace),
        media_type="application/x-ndjson"
    )
