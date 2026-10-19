from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.context import UserContext
from models.response import APIResponse
from agents.orchestrator import OrchestratorAgent

router = APIRouter(prefix="/settle")
orchestrator = OrchestratorAgent()

@router.post("/plan")
async def settle_plan(context: UserContext, trace: bool = False):
    return StreamingResponse(
        orchestrator.stream_settle_plan(context, trace=trace),
        media_type="application/x-ndjson"
    )

@router.post("/healthcare/check", response_model=APIResponse)
async def healthcare_check(context: UserContext, trace: bool = False):
    # Keeping healthcare check as standard POST for now unless stream is specifically requested.
    # But for strict anti-hallucination compliance:
    return APIResponse(
        status="fallback",
        data={"providers": []},
        explanation="Healthcare API integration missing API key. Unable to fetch providers.",
        context_used={"user_id": context.user_id},
        sources=[],
        source_mode="fallback"
    )
