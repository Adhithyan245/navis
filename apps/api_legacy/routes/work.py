from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/work", tags=["work"])

@router.post("/search")
async def work_spaces(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_work(context, trace=trace),
        media_type="application/x-ndjson"
    )
