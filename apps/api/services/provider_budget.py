"""
services/provider_budget.py

Tracks API quota usage per provider and implements adaptive fallback
routing when a provider is approaching exhaustion.

Per-provider counters are in-process (per instance). In a multi-replica
deployment, pair this with a Redis backend for distributed budget sharing.
"""
from __future__ import annotations

import time
import asyncio
from typing import Dict, Any
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

# Default per-minute and daily quota limits (conservative estimates)
_DEFAULT_LIMITS: Dict[str, Dict[str, int]] = {
    "foursquare":       {"per_minute": 60,  "daily": 5_000},
    "geoapify":         {"per_minute": 30,  "daily": 3_000},
    "ticketmaster":     {"per_minute": 20,  "daily": 5_000},
    "eventbrite":       {"per_minute": 20,  "daily": 2_000},
    "groq":             {"per_minute": 30,  "daily": 14_400},
    "huggingface":      {"per_minute": 10,  "daily": 1_000},
    "openrouteservice": {"per_minute": 40,  "daily": 2_500},
    "nominatim":        {"per_minute": 1,   "daily": 1_440},  # 1 req/s
    "mediawiki":        {"per_minute": 200, "daily": 100_000},
}

# Low-watermark below which we emit a quota warning (fraction of daily)
_QUOTA_WARNING_FRACTION = 0.10


class ProviderBudget:
    def __init__(self):
        self._calls: Dict[str, list[float]] = {k: [] for k in _DEFAULT_LIMITS}
        self._daily:  Dict[str, int]        = {k: 0 for k in _DEFAULT_LIMITS}
        self._day_start: float = time.time()
        self._lock = asyncio.Lock()

    async def record_call(self, provider: str) -> None:
        async with self._lock:
            now = time.time()
            # Reset daily counter at midnight
            if now - self._day_start > 86_400:
                self._daily = {k: 0 for k in _DEFAULT_LIMITS}
                self._day_start = now

            if provider in self._calls:
                self._calls[provider].append(now)
                self._daily[provider] = self._daily.get(provider, 0) + 1

    async def is_healthy(self, provider: str) -> bool:
        """True if this provider has not hit per-minute or daily limits."""
        async with self._lock:
            limits = _DEFAULT_LIMITS.get(provider)
            if not limits:
                return True
            now = time.time()
            recent = [t for t in self._calls.get(provider, []) if now - t < 60]
            self._calls[provider] = recent  # prune
            if len(recent) >= limits["per_minute"]:
                logger.warning("Provider per-minute quota hit", provider=provider)
                return False
            if self._daily.get(provider, 0) >= limits["daily"]:
                logger.error("Provider daily quota exhausted", provider=provider)
                return False
            return True

    async def quota_warning(self, provider: str) -> bool:
        """True if daily usage exceeds (1 - warning_fraction) of the limit."""
        async with self._lock:
            limits = _DEFAULT_LIMITS.get(provider)
            if not limits:
                return False
            used = self._daily.get(provider, 0)
            threshold = int(limits["daily"] * (1 - _QUOTA_WARNING_FRACTION))
            return used >= threshold

    def get_metrics(self) -> Dict[str, Any]:
        result = {}
        for provider, limits in _DEFAULT_LIMITS.items():
            used_daily = self._daily.get(provider, 0)
            result[provider] = {
                "daily_used": used_daily,
                "daily_limit": limits["daily"],
                "per_minute_limit": limits["per_minute"],
                "daily_remaining": max(0, limits["daily"] - used_daily),
                "quota_warning": used_daily >= int(limits["daily"] * (1 - _QUOTA_WARNING_FRACTION)),
            }
        return result


provider_budget = ProviderBudget()
