"""
Per-request observability — trace context and execution path tracking.

Architecture:
  - `TraceContext` holds the full call log for ONE request.
  - `_trace_ctx` is a contextvars.ContextVar so each async request gets
    its own isolated context — no cross-request contamination.
  - Orchestrator methods call `get_trace().record_call(...)` to append entries.
  - At stream completion, `build_debug_block()` produces the `debug` payload
    that is embedded in the `completed` event when `?trace=true`.

Usage:
    from core.observability import new_trace, get_trace, build_debug_block

    # At stream entry:
    trace = new_trace(agent="explore", trace_id=request_trace_id)

    # After each provider call:
    get_trace().record_call(
        provider="google_places",
        action="search_places",
        success=True,
        latency_ms=312.4,
        reason=None,
    )

    # At completion:
    debug = build_debug_block()  # None if trace not active
"""

import time
import uuid
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Data structures ───────────────────────────────────────────────────────────

REASON_MISSING_KEY  = "missing_api_key"
REASON_TIMEOUT      = "api_timeout"
REASON_RATE_LIMIT   = "rate_limit"
REASON_NO_RESULTS   = "no_results"
REASON_HTTP_ERROR   = "http_error"
REASON_PARSE_FAILED = "parse_failed"
REASON_UNSUPPORTED  = "unsupported_city"
REASON_SUCCESS      = None  # No reason when successful


@dataclass
class ProviderCall:
    """Record of a single external API call."""
    provider: str
    action: str
    success: bool
    latency_ms: float
    reason: Optional[str] = None   # One of the REASON_* constants above
    detail: Optional[str] = None   # Human-readable extra info


@dataclass
class TraceContext:
    """Full execution trace for a single agent request."""
    trace_id: str
    agent: str
    started_at: float = field(default_factory=time.time)
    calls: List[ProviderCall] = field(default_factory=list)
    fallbacks: List[str] = field(default_factory=list)
    rankings_applied: bool = False
    _active: bool = True

    def record_call(
        self,
        provider: str,
        action: str,
        success: bool,
        latency_ms: float,
        reason: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        self.calls.append(ProviderCall(
            provider=provider,
            action=action,
            success=success,
            latency_ms=latency_ms,
            reason=reason,
            detail=detail,
        ))
        if not success:
            logger.debug(
                "provider_call provider=%s action=%s success=False reason=%s latency_ms=%.1f",
                provider, action, reason, latency_ms,
            )

    def record_fallback(self, provider: str, reason: str) -> None:
        entry = f"{provider}:{reason}"
        self.fallbacks.append(entry)
        logger.info(
            "fallback_triggered agent=%s provider=%s reason=%s",
            self.agent, provider, reason,
        )

    def elapsed_ms(self) -> float:
        return round((time.time() - self.started_at) * 1000, 1)

    def to_debug_block(self) -> Dict[str, Any]:
        total_ms = self.elapsed_ms()
        providers_used = list({c.provider for c in self.calls if c.success})
        providers_failed = list({c.provider for c in self.calls if not c.success})

        call_log = [
            {
                "provider": c.provider,
                "action": c.action,
                "success": c.success,
                "latency_ms": round(c.latency_ms, 1),
                **({"reason": c.reason} if c.reason else {}),
                **({"detail": c.detail} if c.detail else {}),
            }
            for c in self.calls
        ]

        return {
            "trace_id": self.trace_id,
            "agent": self.agent,
            "total_latency_ms": total_ms,
            "providers_used": providers_used,
            "providers_failed": providers_failed,
            "fallbacks_triggered": self.fallbacks,
            "rankings_applied": self.rankings_applied,
            "call_log": call_log,
        }


# ── Context variable — one per async request ──────────────────────────────────

_trace_ctx: ContextVar[Optional[TraceContext]] = ContextVar("_trace_ctx", default=None)


def new_trace(agent: str, trace_id: Optional[str] = None) -> TraceContext:
    """
    Create a new TraceContext for this request and bind it to the current
    async context. Must be called at the start of each stream method when
    trace mode is active.
    """
    trace = TraceContext(
        trace_id=trace_id or str(uuid.uuid4())[:8],
        agent=agent,
    )
    _trace_ctx.set(trace)
    return trace


def get_trace() -> Optional[TraceContext]:
    """Return the active TraceContext for this request, or None if not tracing."""
    return _trace_ctx.get()


def build_debug_block() -> Optional[Dict[str, Any]]:
    """
    Build the `debug` payload for the `completed` stream event.
    Returns None if no trace is active (trace=false requests).
    """
    trace = get_trace()
    if trace is None:
        return None
    return trace.to_debug_block()


def classify_service_reason(service_response: dict) -> Optional[str]:
    """
    Infer a machine-readable `reason` from a service layer response dict.

    Service responses follow the pattern:
        {"status": "fallback", "explanation": "...", ...}

    This maps the explanation text to a structured reason code.
    """
    if service_response.get("status") == "success":
        return None

    explanation = (service_response.get("explanation") or "").lower()

    if any(kw in explanation for kw in ["api key", "not configured", "missing"]):
        return REASON_MISSING_KEY
    if "timed out" in explanation or "timeout" in explanation:
        return REASON_TIMEOUT
    if "rate limit" in explanation or "429" in explanation:
        return REASON_RATE_LIMIT
    if any(kw in explanation for kw in ["no ", "zero result", "not found", "empty"]):
        return REASON_NO_RESULTS
    if any(kw in explanation for kw in ["http", "status code", "error:"]):
        return REASON_HTTP_ERROR

    return "unknown"
