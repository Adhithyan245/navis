from pydantic import BaseModel
from typing import Any, Dict, Literal, Optional

StreamState = Literal[
    "understanding_request",
    "fetching_live_data",
    "ranking_results",
    "merging_outputs",

    # Existing orchestration states
    "routing_agent",
    "system_check",
    "fallback_triggered",

    # Phase-2 planner lifecycle states
    "planner_started",
    "agent_started",
    "agent_completed",
    "agent_failed",
    "fusion_completed",
    "verification_completed",
    "humanization_completed",

    # Final terminal state
    "completed",
]

class StreamEvent(BaseModel):
    state: StreamState
    progress: int
    data: Optional[Dict[str, Any]] = None

