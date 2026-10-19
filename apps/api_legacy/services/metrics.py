"""
Operational metrics collector.

Extends source audit logging with latency, failure rates, and domain-level stats.
All data is stored in-memory for the process lifetime; persisted via SourceAuditLog.
"""

import time
from typing import Any, Dict, List
from collections import defaultdict


class MetricsCollector:
    def __init__(self):
        self._provider_latency: Dict[str, List[float]] = defaultdict(list)
        self._provider_failures: Dict[str, int] = defaultdict(int)
        self._provider_successes: Dict[str, int] = defaultdict(int)
        self._fallback_count: Dict[str, int] = defaultdict(int)
        self._unsupported_cities: Dict[str, int] = defaultdict(int)
        self._empty_state_count: Dict[str, int] = defaultdict(int)
        self._cross_domain_success: int = 0
        self._cross_domain_failure: int = 0
        
        # Advanced Phase 2 Observability
        self._memory_latency: List[float] = []
        self._planner_graph_depths: List[int] = []
        self._orchestration_fanout: List[int] = []
        self._inference_latencies: List[float] = []
        self._hallucination_suppression_count: int = 0
        self._provider_confidence_degradation: List[float] = []

    def record_memory_retrieval(self, latency_ms: float):
        self._memory_latency.append(latency_ms)
        
    def record_planner_graph(self, depth: int, fanout: int):
        self._planner_graph_depths.append(depth)
        self._orchestration_fanout.append(fanout)
        
    def record_inference(self, latency_ms: float):
        self._inference_latencies.append(latency_ms)
        
    def record_hallucination_suppression(self):
        self._hallucination_suppression_count += 1
        
    def record_confidence_degradation(self, degradation_amount: float):
        self._provider_confidence_degradation.append(degradation_amount)

    def record_provider_call(self, provider: str, latency_ms: float, success: bool):
        self._provider_latency[provider].append(latency_ms)
        if success:
            self._provider_successes[provider] += 1
        else:
            self._provider_failures[provider] += 1

    def record_fallback(self, domain: str):
        self._fallback_count[domain] += 1

    def record_empty_state(self, domain: str):
        self._empty_state_count[domain] += 1

    def record_unsupported_city(self, city: str):
        self._unsupported_cities[city.lower().strip()] += 1

    def record_cross_domain(self, success: bool):
        if success:
            self._cross_domain_success += 1
        else:
            self._cross_domain_failure += 1

    def get_provider_stats(self, provider: str) -> Dict[str, Any]:
        latencies = self._provider_latency.get(provider, [])
        return {
            "total_calls": len(latencies),
            "successes": self._provider_successes.get(provider, 0),
            "failures": self._provider_failures.get(provider, 0),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 1),
        }

    def get_summary(self) -> Dict[str, Any]:
        providers = set(
            list(self._provider_latency.keys()) +
            list(self._provider_failures.keys()) +
            list(self._provider_successes.keys())
        )
        
        avg_memory_latency = round(sum(self._memory_latency) / len(self._memory_latency), 1) if self._memory_latency else 0
        avg_inference_latency = round(sum(self._inference_latencies) / len(self._inference_latencies), 1) if self._inference_latencies else 0
        avg_planner_depth = round(sum(self._planner_graph_depths) / len(self._planner_graph_depths), 1) if self._planner_graph_depths else 0
        avg_fanout = round(sum(self._orchestration_fanout) / len(self._orchestration_fanout), 1) if self._orchestration_fanout else 0
        
        return {
            "providers": {p: self.get_provider_stats(p) for p in providers},
            "fallback_by_domain": dict(self._fallback_count),
            "empty_state_by_domain": dict(self._empty_state_count),
            "unsupported_city_requests": dict(self._unsupported_cities),
            "cross_domain": {
                "success": self._cross_domain_success,
                "failure": self._cross_domain_failure,
            },
            "advanced": {
                "avg_memory_latency_ms": avg_memory_latency,
                "avg_inference_latency_ms": avg_inference_latency,
                "avg_planner_graph_depth": avg_planner_depth,
                "avg_orchestration_fanout": avg_fanout,
                "hallucination_suppression_count": self._hallucination_suppression_count,
            }
        }


# Singleton instance
metrics = MetricsCollector()
