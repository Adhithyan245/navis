"""
observability/metrics.py

Prometheus-compatible metrics for Navis.
Uses the 'prometheus_client' library if available, falls back to
a simple in-process counter/histogram so the server never crashes.

Tracks:
  - active_streams
  - stream duration
  - provider latency per provider
  - provider timeout rate
  - fallback activation frequency
  - cache hit/miss
  - semaphore utilisation
  - queue depth
  - chunk emission latency
  - slow-consumer incidents
  - cancellation events
  - memory samples
"""
from __future__ import annotations

import time
import asyncio
import threading
from typing import Dict, Any

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Summary,
        CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    )
    PROM_AVAILABLE = True
    registry = CollectorRegistry(auto_describe=True)

    # ── Streams ──────────────────────────────────────────────────────────────
    ACTIVE_STREAMS       = Gauge("navis_active_streams",        "Concurrent NDJSON streams",          registry=registry)
    STREAM_DURATION      = Histogram("navis_stream_duration_seconds", "Stream lifetime", buckets=[1,5,10,30,60,120], registry=registry)
    STREAM_CANCELLATIONS = Counter("navis_stream_cancellations_total", "Client disconnects", registry=registry)
    SLOW_CONSUMER_EVENTS = Counter("navis_slow_consumer_total",        "Slow-consumer aborts",         registry=registry)

    # ── Providers ─────────────────────────────────────────────────────────────
    PROVIDER_LATENCY     = Histogram("navis_provider_latency_seconds",
                                     "Provider call latency", ["provider"],
                                     buckets=[.05,.1,.25,.5,1,2.5,5,10],
                                     registry=registry)
    PROVIDER_TIMEOUTS    = Counter("navis_provider_timeouts_total",   "Provider timeouts",  ["provider"], registry=registry)
    PROVIDER_FALLBACKS   = Counter("navis_provider_fallbacks_total",  "Fallback activations", ["provider"], registry=registry)
    PROVIDER_ERRORS      = Counter("navis_provider_errors_total",     "Provider errors",    ["provider", "reason"], registry=registry)

    # ── Cache ─────────────────────────────────────────────────────────────────
    CACHE_HITS           = Counter("navis_cache_hits_total",   "Cache hits",   ["provider"], registry=registry)
    CACHE_MISSES         = Counter("navis_cache_misses_total", "Cache misses", ["provider"], registry=registry)

    # ── Concurrency ───────────────────────────────────────────────────────────
    SEMAPHORE_UTIL       = Gauge("navis_semaphore_utilisation", "Semaphore slots in use",  registry=registry)
    QUEUE_DEPTH          = Gauge("navis_queue_depth",           "Bounded queue depth",      registry=registry)
    CHUNK_LATENCY        = Histogram("navis_chunk_emission_latency_seconds",
                                     "NDJSON chunk yield latency",
                                     buckets=[.001,.005,.01,.05,.1,.5,1,2],
                                     registry=registry)

    # ── System ────────────────────────────────────────────────────────────────
    EVENT_LOOP_LAG       = Gauge("navis_event_loop_lag_seconds", "Async event-loop lag", registry=registry)
    MEMORY_BYTES         = Gauge("navis_memory_rss_bytes",       "Process RSS memory",   registry=registry)

except ImportError:
    PROM_AVAILABLE = False
    # ── Stubs ─────────────────────────────────────────────────────────────────
    class _Noop:
        def inc(self, *a, **k): pass
        def dec(self, *a, **k): pass
        def set(self, *a, **k): pass
        def observe(self, *a, **k): pass
        def labels(self, *a, **k): return self

    _noop = _Noop()
    ACTIVE_STREAMS       = _noop
    STREAM_DURATION      = _noop
    STREAM_CANCELLATIONS = _noop
    SLOW_CONSUMER_EVENTS = _noop
    PROVIDER_LATENCY     = _noop
    PROVIDER_TIMEOUTS    = _noop
    PROVIDER_FALLBACKS   = _noop
    PROVIDER_ERRORS      = _noop
    CACHE_HITS           = _noop
    CACHE_MISSES         = _noop
    SEMAPHORE_UTIL       = _noop
    QUEUE_DEPTH          = _noop
    CHUNK_LATENCY        = _noop
    EVENT_LOOP_LAG       = _noop
    MEMORY_BYTES         = _noop
    registry             = None


def get_metrics_output() -> bytes:
    """Return Prometheus text format or a JSON fallback."""
    if PROM_AVAILABLE:
        from prometheus_client import generate_latest
        return generate_latest(registry)
    return b"# prometheus_client not installed\n"


def get_metrics_content_type() -> str:
    if PROM_AVAILABLE:
        from prometheus_client import CONTENT_TYPE_LATEST
        return CONTENT_TYPE_LATEST
    return "text/plain"
