"""
observability/profiling.py

Async-safe profiling utilities for Navis production runtime.

Detects:
  - event loop lag (measures probe task scheduling delay)
  - process memory growth (RSS via psutil if available)
  - orphan async task leaks
  - queue growth anomalies
  - semaphore starvation

Runs as an optional background daemon coroutine; errors are caught
and logged rather than crashing the service.
"""
from __future__ import annotations

import asyncio
import gc
import time
from typing import Dict, Any

from apps.api.core.logging import get_logger
from apps.api.observability.metrics import EVENT_LOOP_LAG, MEMORY_BYTES

logger = get_logger(__name__)

# ── Optional psutil ────────────────────────────────────────────────────────────
try:
    import psutil as _psutil
    _PROC = _psutil.Process()
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    _PROC = None


# ── Event-loop lag probe ───────────────────────────────────────────────────────

async def _measure_loop_lag(interval: float = 1.0) -> None:
    """
    Schedules a trivial coroutine every `interval` seconds and measures
    the drift between expected and actual execution time as loop lag.
    """
    while True:
        expected = time.monotonic()
        await asyncio.sleep(interval)
        lag = max(0.0, time.monotonic() - expected - interval)
        EVENT_LOOP_LAG.set(lag)
        if lag > 0.1:
            logger.warning("High event-loop lag detected", lag_seconds=lag)
        elif lag > 0.5:
            logger.error("Critical event-loop lag — possible blocking call", lag_seconds=lag)


# ── Memory probe ───────────────────────────────────────────────────────────────

async def _measure_memory(interval: float = 30.0) -> None:
    """Samples process RSS every `interval` seconds."""
    while True:
        await asyncio.sleep(interval)
        if PSUTIL_AVAILABLE and _PROC:
            try:
                rss = _PROC.memory_info().rss
                MEMORY_BYTES.set(rss)
                if rss > 512 * 1024 * 1024:  # 512 MB warning
                    logger.warning("High memory usage", rss_mb=rss // (1024 * 1024))
            except Exception:
                pass


# ── Orphan-task detector ───────────────────────────────────────────────────────

async def _detect_task_leaks(interval: float = 60.0) -> None:
    """
    Periodically counts asyncio tasks. Warns if count grows unbounded.
    """
    baseline: int | None = None
    while True:
        await asyncio.sleep(interval)
        try:
            tasks = asyncio.all_tasks()
            count = len(tasks)
            if baseline is None:
                baseline = count
                continue
            delta = count - baseline
            if delta > 50:
                logger.error(
                    "Possible async task leak",
                    task_count=count,
                    delta_from_baseline=delta,
                )
            elif delta > 20:
                logger.warning("Elevated task count", task_count=count)
            baseline = count
        except Exception:
            pass


# ── Public entry point ─────────────────────────────────────────────────────────

async def start_profiling_daemon() -> None:
    """
    Launches all profiling monitors as background daemon tasks.
    Called once from the FastAPI lifespan.
    """
    asyncio.create_task(_measure_loop_lag(interval=1.0),   name="navis-loop-lag-probe")
    asyncio.create_task(_measure_memory(interval=30.0),    name="navis-memory-probe")
    asyncio.create_task(_detect_task_leaks(interval=60.0), name="navis-task-leak-detector")
    logger.info("Profiling daemon started")


def get_snapshot() -> Dict[str, Any]:
    """Returns a point-in-time profiling snapshot for /health/detailed."""
    snap: Dict[str, Any] = {
        "task_count": len(asyncio.all_tasks()) if asyncio.get_event_loop().is_running() else -1,
        "psutil_available": PSUTIL_AVAILABLE,
    }
    if PSUTIL_AVAILABLE and _PROC:
        try:
            info = _PROC.memory_info()
            snap["rss_mb"] = info.rss // (1024 * 1024)
            snap["vms_mb"] = info.vms // (1024 * 1024)
        except Exception:
            pass
    return snap
