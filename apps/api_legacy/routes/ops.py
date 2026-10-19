"""
Operational endpoints.

GET /ops/metrics   — raw MetricsCollector summary + cache stats
GET /system/health — human + machine-readable system health snapshot
"""

from fastapi import APIRouter
from services.metrics import metrics
from services.cache import cache_stats
from services.provider_base import registry

router = APIRouter(prefix="/ops", tags=["ops"])

# Agents that have dedicated streaming endpoints
_ALL_AGENTS = [
    "explore", "taste", "connect", "services", "move",
    "transit", "work", "settle", "voice",
]

async def _agent_health(agent: str) -> str:
    """
    Classify agent health based on provider availability.
    With Open Infrastructure, primary providers are always ACTIVE.
    """
    primary = registry.get_primary_provider(agent)
    if primary and primary.is_configured():
        return "ACTIVE"
    return "LIMITED"

@router.get("/metrics")
async def get_metrics():
    """Raw MetricsCollector summary + cache statistics."""
    return {"metrics": metrics.get_summary(), "cache": cache_stats()}

@router.get("/system/health")
async def system_health():
    """
    Structured system health snapshot.
    """
    # Get all registered providers and their configured status
    providers = {p_id: p.is_configured() for p_id, p in registry._providers.items()}
    
    agent_health = {agent: await _agent_health(agent) for agent in _ALL_AGENTS}

    # Aggregate latency and error rate across all providers
    summary = metrics.get_summary()
    provider_stats = summary.get("providers", {})

    all_latencies: list[float] = []
    total_calls = 0
    total_failures = 0

    for pname, pstats in provider_stats.items():
        calls = pstats.get("total_calls", 0)
        failures = pstats.get("failures", 0)
        avg_lat = pstats.get("avg_latency_ms", 0)
        if calls > 0:
            all_latencies.extend([avg_lat] * calls)
        total_calls += calls
        total_failures += failures

    avg_latency = round(sum(all_latencies) / len(all_latencies), 1) if all_latencies else 0
    error_rate = round(total_failures / total_calls, 3) if total_calls > 0 else 0.0

    fallback_counts = summary.get("fallback_by_domain", {})
    total_fallbacks = sum(fallback_counts.values())

    active_count = sum(1 for v in agent_health.values() if v == 'ACTIVE')
    provider_count = sum(1 for v in providers.values() if v)

    return {
        "status": "success",
        "data": {
            "agents": agent_health,
            "providers": providers,
            "metrics": {
                "avg_latency_ms": avg_latency,
                "error_rate": error_rate,
                "total_api_calls": total_calls,
                "total_fallbacks": total_fallbacks,
                "fallback_by_agent": fallback_counts,
            },
            "cache": cache_stats(),
        },
        "explanation": (
            f"{active_count}/{len(_ALL_AGENTS)} agents ACTIVE. "
            f"{provider_count}/{len(providers)} providers configured."
        ),
        "context_used": {},
        "sources": [],
        "source_mode": "live",
        "reason": None,
    }
