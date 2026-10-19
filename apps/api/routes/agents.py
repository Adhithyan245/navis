"""
routes/agents.py — the agent catalog and its operational health.

  GET /v2/agents          public: what Navis can do (user-facing agents)
  GET /v2/agents/health   internal (X-Internal-Auth): per-agent runs,
                          outcomes, latency percentiles, breaker state
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from apps.api.agentic import metrics
from apps.api.agentic.catalog import registry
from apps.api.services.accounts import internal_secret_ok

router = APIRouter(prefix="/v2/agents", tags=["Agents"])


@router.get("")
async def list_agents() -> dict:
    return {"agents": [
        {"name": m.name, "domain": m.domain, "title": m.title,
         "description": m.description, "capabilities": list(m.capabilities)}
        for m in registry.manifests() if m.user_facing
    ]}


@router.get("/health")
async def agents_health(x_internal_auth: Optional[str] = Header(None)) -> dict:
    if not internal_secret_ok(x_internal_auth):
        raise HTTPException(status_code=403, detail="Forbidden")
    stats = metrics.snapshot()
    return {"agents": {
        m.name: {"domain": m.domain, "workflow": m.workflow, "timeout_s": m.timeout_s,
                 **stats.get(m.name, {"runs": 0, "outcomes": {}, "circuit": "closed"})}
        for m in registry.manifests()
    }}
