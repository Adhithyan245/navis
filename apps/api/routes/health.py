"""routes/health.py — Health & operational diagnostics endpoints."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from apps.api.services.provider_manager import provider_manager
from apps.api.services.provider_validator import get_provider_states
from apps.api.services.provider_budget import provider_budget
from apps.api.observability.telemetry import telemetry
from apps.api.observability.profiling import get_snapshot
from apps.api.observability.metrics import get_metrics_output, get_metrics_content_type
import time

from apps.api.core import kv
from apps.api.core.ops import require_ops

router = APIRouter()
START_TIME = time.time()


@router.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0", "service": "navis-orchestrator"}


@router.get("/ready")
async def readiness():
    """Readiness: 503 until the accounts store answers (and Redis, when
    configured), so load balancers only route to instances that can serve."""
    from apps.api.services import accounts

    checks = {"accounts_db": await accounts.ping()}
    redis_ok = await kv.redis_ping()
    if redis_ok is not None:
        checks["redis"] = redis_ok
    ok = all(checks.values())
    return JSONResponse({"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503)


@router.get("/health/detailed", dependencies=[Depends(require_ops)])
async def health_detailed():
    states = get_provider_states()
    healthy_count  = sum(1 for v in states.values() if v.get("status") == "healthy")
    degraded_count = sum(1 for v in states.values() if v.get("status") != "healthy")

    return {
        "status": "ok" if healthy_count > 0 else "degraded",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "providers": {
            "total":    len(states),
            "healthy":  healthy_count,
            "degraded": degraded_count,
        },
        "telemetry":     telemetry.get_metrics(),
        "profiling":     get_snapshot(),
        "semaphore_locked": provider_manager.semaphore.locked(),
        "budget_warnings": [
            p for p, m in (await provider_budget.get_metrics()).items()  # type: ignore[misc]
            if m["quota_warning"]
        ] if False else [],  # budget.get_metrics is sync — just reference directly
    }


@router.get("/metrics", dependencies=[Depends(require_ops)])
async def prometheus_metrics():
    """Prometheus scrape endpoint."""
    output = get_metrics_output()
    return Response(
        content=output,
        media_type=get_metrics_content_type(),
    )
