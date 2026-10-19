"""
Global safety utilities for Navis orchestration pipeline.

These functions are designed to NEVER throw exceptions.
Import and use across all modules for consistent null-safety.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ─── Valid StreamState values (must mirror models/stream.py) ────────────────
_VALID_STREAM_STATES = frozenset({
    "understanding_request",
    "fetching_live_data",
    "ranking_results",
    "merging_outputs",
    "routing_agent",
    "system_check",
    "fallback_triggered",
    "planner_started",
    "agent_started",
    "agent_completed",
    "agent_failed",
    "fusion_completed",
    "verification_completed",
    "humanization_completed",
    "completed",
})

_FALLBACK_STATE = "system_check"


def safe_user_id(raw: Any) -> int:
    """
    Parse user_id safely — NEVER throws.

    Rules:
    - None → -1
    - empty string → -1
    - non-numeric string → -1
    - valid numeric string → int
    - any other type → -1
    """
    if not raw:
        return -1
    try:
        s = str(raw).strip()
        return int(s) if s.isdigit() else -1
    except Exception:
        return -1


def safe_emit_event(state: str, progress: int, data: Optional[Dict[str, Any]] = None) -> str:
    """
    Build a safe NDJSON StreamEvent line.
    - Validates state against known StreamState literals
    - Falls back to 'system_check' for unknown states
    - NEVER throws — always returns valid JSON line

    Returns: JSON string + newline (ready to yield)
    """
    try:
        from models.stream import StreamEvent

        # Sanitize state
        if state not in _VALID_STREAM_STATES:
            logger.warning("safe_emit_event: unknown state '%s' → falling back to '%s'", state, _FALLBACK_STATE)
            state = _FALLBACK_STATE

        # Clamp progress
        progress = max(0, min(100, int(progress)))

        return StreamEvent(state=state, progress=progress, data=data).model_dump_json() + "\n"
    except Exception as e:
        # Absolute last resort — hand-build minimal JSON
        logger.error("safe_emit_event: StreamEvent construction failed: %s", e)
        import json
        fallback = {
            "state": _FALLBACK_STATE,
            "progress": max(0, min(100, int(progress))) if isinstance(progress, (int, float)) else 0,
            "data": None,
        }
        return json.dumps(fallback) + "\n"


def safe_context_field(context: Any, field: str, default: Any = None) -> Any:
    """
    Safely read a field from a context object or dict.
    NEVER throws.
    """
    try:
        if hasattr(context, field):
            val = getattr(context, field)
            return val if val is not None else default
        if isinstance(context, dict):
            val = context.get(field)
            return val if val is not None else default
        return default
    except Exception:
        return default
