"""
Per-agent operational metrics: runs, outcome counts, latency, last failure.

In-process (exposed via GET /v2/agents/health) and mirrored to Prometheus
when prometheus_client is installed (navis_agent_runs_total,
navis_agent_latency_seconds).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict

try:
    from prometheus_client import Counter, Histogram

    from apps.api.observability.metrics import registry as _prom_registry

    _RUNS = Counter("navis_agent_runs_total", "Agent runs by outcome", ["agent", "outcome"],
                    registry=_prom_registry)
    _LATENCY = Histogram("navis_agent_latency_seconds", "Agent latency", ["agent"],
                         buckets=[.1, .25, .5, 1, 2, 5, 10, 20, 45], registry=_prom_registry)
except Exception:  # noqa: BLE001 — metrics must never break agents
    _RUNS = _LATENCY = None

_WINDOW = 200


class AgentStats:
    def __init__(self) -> None:
        self.outcomes: Dict[str, int] = defaultdict(int)
        self.latencies: Deque[float] = deque(maxlen=_WINDOW)
        self.last_failure_at: float | None = None
        self.consecutive_failures = 0
        self.open_until = 0.0

    def snapshot(self) -> Dict[str, Any]:
        lat = sorted(self.latencies)

        def pct(p: float) -> float | None:
            return round(lat[min(len(lat) - 1, int(p * len(lat)))], 3) if lat else None

        return {
            "runs": sum(self.outcomes.values()),
            "outcomes": dict(self.outcomes),
            "latency_p50_s": pct(0.5),
            "latency_p95_s": pct(0.95),
            "last_failure_at": self.last_failure_at,
            "circuit": "open" if time.time() < self.open_until else "closed",
        }


_stats: Dict[str, AgentStats] = defaultdict(AgentStats)

# Simple per-agent circuit breaker: after N consecutive failures (exceptions
# or timeouts), skip the agent for a cool-down so a broken dependency
# doesn't slow every request.
BREAKER_THRESHOLD = 3
BREAKER_COOLDOWN_S = 60.0


def is_open(agent: str) -> bool:
    return time.time() < _stats[agent].open_until


def record(agent: str, outcome: str, seconds: float) -> None:
    """outcome: ok | partial | empty | unavailable | error | timeout | skipped"""
    s = _stats[agent]
    s.outcomes[outcome] += 1
    if outcome != "skipped":
        s.latencies.append(seconds)
    if outcome in ("error", "timeout"):
        s.consecutive_failures += 1
        s.last_failure_at = time.time()
        if s.consecutive_failures >= BREAKER_THRESHOLD:
            s.open_until = time.time() + BREAKER_COOLDOWN_S
    elif outcome != "skipped":
        s.consecutive_failures = 0
    if _RUNS is not None:
        try:
            _RUNS.labels(agent=agent, outcome=outcome).inc()
            if outcome != "skipped":
                _LATENCY.labels(agent=agent).observe(seconds)
        except Exception:  # noqa: BLE001
            pass


def snapshot() -> Dict[str, Dict[str, Any]]:
    return {name: s.snapshot() for name, s in sorted(_stats.items())}


def reset() -> None:
    _stats.clear()
