from fastapi import APIRouter
from core.config import settings
from models.response import APIResponse

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Basic liveness probe.
    Returns HTTP 200 with status 'success' when the server is reachable.
    For full system state (API keys, per-agent health), use GET /system/health.
    """
    providers = settings.active_providers()
    configured = [k for k, v in providers.items() if v]
    return {
        "status": "success",
        "data": {
            "alive": True,
            "providers_configured": len(configured),
            "providers": providers,
        },
        "explanation": f"Server is healthy. {len(configured)}/{len(providers)} providers configured.",
        "context_used": {},
        "sources": [],
        "source_mode": "fallback",
        "reason": None,
    }

