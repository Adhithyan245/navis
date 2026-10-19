from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/services", tags=["services"])

@router.post("/search")
async def essential_services(context: UserContext, trace: bool = False):
    agent = OrchestratorAgent()
    return StreamingResponse(
        agent.stream_services(context, trace=trace),
        media_type="application/x-ndjson"
    )
