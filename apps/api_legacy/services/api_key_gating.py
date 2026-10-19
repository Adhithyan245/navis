"""
PHASE 3: API Key Gating & Quota Management

Centralized control over API key validation, rate limiting, and quota tracking.
Ensures only authorized calls reach external providers.

Architecture:
1. API Key Registry - track which keys are configured for which providers
2. Rate Limiter - enforce call rate limits per provider/key
3. Quota Tracker - track usage and prevent quota exhaustion
4. Gating Service - orchestrate validation before external calls
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field

from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class QuotaLimit:
    """Quota limits for a provider/key combination."""
    requests_per_day: int = 1000
    requests_per_minute: int = 100
    max_concurrent: int = 10


@dataclass
class QuotaUsage:
    """Tracks quota usage over time."""
    requests_today: int = 0
    requests_this_minute: int = 0
    concurrent_requests: int = 0
    last_reset_day: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    last_reset_minute: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    call_history: list = field(default_factory=list)  # Track last 100 calls for debugging


class APIKeyRegistry:
    """Manages API keys and their configured providers."""

    def __init__(self):
        self.keys: Dict[str, Dict[str, Any]] = {}
        self._load_from_config()

    def _load_from_config(self) -> None:
        """Load API keys from settings."""
        # Google Places
        if settings.google_places_api_key:
            self.keys["google_places"] = {
                "key": settings.google_places_api_key[:10] + "...",  # Masked for logging
                "provider": "google_places",
                "configured": True,
                "status": "active",
            }

        # Yelp
        if settings.yelp_api_key:
            self.keys["yelp"] = {
                "key": settings.yelp_api_key[:10] + "...",
                "provider": "yelp",
                "configured": True,
                "status": "active",
            }

        # EventBrite
        if settings.eventbrite_api_key:
            self.keys["eventbrite"] = {
                "key": settings.eventbrite_api_key[:10] + "...",
                "provider": "eventbrite",
                "configured": True,
                "status": "active",
            }

        # Ticketmaster
        if settings.ticketmaster_api_key:
            self.keys["ticketmaster"] = {
                "key": settings.ticketmaster_api_key[:10] + "...",
                "provider": "ticketmaster",
                "configured": True,
                "status": "active",
            }

        # MBTA
        if settings.mbta_api_key:
            self.keys["mbta"] = {
                "key": settings.mbta_api_key[:10] + "...",
                "provider": "mbta",
                "configured": True,
                "status": "active",
            }

        # Adzuna
        if settings.adzuna_app_id and settings.adzuna_app_key:
            self.keys["adzuna"] = {
                "key": f"app_id:{settings.adzuna_app_id[:5]}...",
                "provider": "adzuna",
                "configured": True,
                "status": "active",
            }

    def is_configured(self, provider: str) -> bool:
        """Check if provider has a configured API key."""
        key_info = self.keys.get(provider, {})
        return key_info.get("configured", False)

    def get_key(self, provider: str) -> Optional[str]:
        """Get actual API key for provider (unmasked)."""
        if provider == "google_places":
            return settings.google_places_api_key
        elif provider == "yelp":
            return settings.yelp_api_key
        elif provider == "eventbrite":
            return settings.eventbrite_api_key
        elif provider == "ticketmaster":
            return settings.ticketmaster_api_key
        elif provider == "mbta":
            return settings.mbta_api_key
        elif provider == "adzuna":
            return settings.adzuna_app_id  # Special handling
        return None

    def list_configured(self) -> Dict[str, Dict[str, Any]]:
        """List all configured providers."""
        return {k: v for k, v in self.keys.items() if v.get("configured")}

    def mark_key_error(self, provider: str, error: str) -> None:
        """Mark provider key as having errors."""
        if provider in self.keys:
            self.keys[provider]["status"] = "error"
            self.keys[provider]["last_error"] = error
            logger.warning(f"Provider '{provider}' marked with error: {error}")


class RateLimiter:
    """Rate limiting for API calls to prevent service degradation."""

    def __init__(self):
        self.call_times: Dict[str, list] = defaultdict(list)  # provider -> [timestamps]
        self.limits: Dict[str, Dict[str, int]] = {
            "google_places": {"per_second": 10, "per_minute": 100},
            "yelp": {"per_second": 5, "per_minute": 50},
            "eventbrite": {"per_second": 5, "per_minute": 50},
            "ticketmaster": {"per_second": 5, "per_minute": 50},
            "mbta": {"per_second": 20, "per_minute": 200},
            "wikipedia": {"per_second": 10, "per_minute": 100},
            "osm": {"per_second": 10, "per_minute": 100},
        }

    def can_make_request(self, provider: str) -> Tuple[bool, Optional[str]]:
        """
        Check if provider rate limit allows a new request.
        
        Returns:
            (allowed, reason_if_denied)
        """
        now = time.time()
        limit = self.limits.get(provider, {"per_second": 5, "per_minute": 50})

        # Clean old calls (older than 1 minute)
        self.call_times[provider] = [t for t in self.call_times[provider] if now - t < 60]

        # Check per-second limit (last 1 second)
        recent_calls = [t for t in self.call_times[provider] if now - t < 1]
        if len(recent_calls) >= limit["per_second"]:
            return False, f"Rate limit: {limit['per_second']} calls/second for {provider}"

        # Check per-minute limit
        if len(self.call_times[provider]) >= limit["per_minute"]:
            return False, f"Rate limit: {limit['per_minute']} calls/minute for {provider}"

        return True, None

    def record_request(self, provider: str) -> None:
        """Record a request for rate limiting."""
        self.call_times[provider].append(time.time())

    def get_stats(self, provider: str) -> Dict[str, Any]:
        """Get rate limiting stats for provider."""
        now = time.time()
        calls_this_minute = [t for t in self.call_times[provider] if now - t < 60]
        calls_this_second = [t for t in self.call_times[provider] if now - t < 1]

        limit = self.limits.get(provider, {"per_second": 5, "per_minute": 50})

        return {
            "provider": provider,
            "calls_this_second": len(calls_this_second),
            "limit_per_second": limit["per_second"],
            "calls_this_minute": len(calls_this_minute),
            "limit_per_minute": limit["per_minute"],
            "utilization_second": len(calls_this_second) / limit["per_second"],
            "utilization_minute": len(calls_this_minute) / limit["per_minute"],
        }


class QuotaTracker:
    """Tracks API quota usage and prevents quota exhaustion."""

    def __init__(self):
        self.usage: Dict[str, QuotaUsage] = {}
        self.limits: Dict[str, QuotaLimit] = {}
        self._init_limits()

    def _init_limits(self) -> None:
        """Initialize quota limits per provider."""
        # Most providers have free tier limits
        self.limits["google_places"] = QuotaLimit(
            requests_per_day=25000,
            requests_per_minute=100,
        )
        self.limits["yelp"] = QuotaLimit(
            requests_per_day=5000,
            requests_per_minute=60,
        )
        self.limits["eventbrite"] = QuotaLimit(
            requests_per_day=5000,
            requests_per_minute=60,
        )
        self.limits["ticketmaster"] = QuotaLimit(
            requests_per_day=5000,
            requests_per_minute=60,
        )
        self.limits["mbta"] = QuotaLimit(
            requests_per_day=50000,
            requests_per_minute=1000,
        )
        self.limits["wikipedia"] = QuotaLimit(
            requests_per_day=100000,
            requests_per_minute=1000,
        )
        self.limits["osm"] = QuotaLimit(
            requests_per_day=50000,
            requests_per_minute=1000,
        )

    def can_use_quota(self, provider: str) -> Tuple[bool, Optional[str]]:
        """
        Check if provider quota allows a new request.
        
        Returns:
            (allowed, reason_if_denied)
        """
        if provider not in self.usage:
            self.usage[provider] = QuotaUsage()
        if provider not in self.limits:
            # Unknown provider — assume quota OK (will be caught by rate limiter)
            return True, None

        usage = self.usage[provider]
        limit = self.limits[provider]

        # Check daily quota
        today = datetime.now().strftime("%Y-%m-%d")
        if usage.last_reset_day != today:
            # Reset daily counter
            usage.requests_today = 0
            usage.last_reset_day = today

        if usage.requests_today >= limit.requests_per_day:
            return False, f"Daily quota exhausted: {limit.requests_per_day} requests/day for {provider}"

        # Check per-minute quota
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if usage.last_reset_minute != now:
            # Reset per-minute counter
            usage.requests_this_minute = 0
            usage.last_reset_minute = now

        if usage.requests_this_minute >= limit.requests_per_minute:
            return False, f"Per-minute quota exhausted: {limit.requests_per_minute} requests/minute for {provider}"

        # Check concurrent requests
        if usage.concurrent_requests >= limit.max_concurrent:
            return False, f"Max concurrent requests reached: {limit.max_concurrent} for {provider}"

        return True, None

    def record_request(self, provider: str) -> None:
        """Record a request against quota."""
        if provider not in self.usage:
            self.usage[provider] = QuotaUsage()

        usage = self.usage[provider]
        usage.requests_today += 1
        usage.requests_this_minute += 1

        # Keep call history for debugging
        if len(usage.call_history) >= 100:
            usage.call_history.pop(0)
        usage.call_history.append({
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
        })

    def record_concurrent_request(self, provider: str, increment: int = 1) -> None:
        """Record concurrent request (increment on start, decrement on end)."""
        if provider not in self.usage:
            self.usage[provider] = QuotaUsage()
        self.usage[provider].concurrent_requests += increment

    def get_usage(self, provider: str) -> Dict[str, Any]:
        """Get detailed quota usage for provider."""
        if provider not in self.usage:
            self.usage[provider] = QuotaUsage()
        if provider not in self.limits:
            return {"provider": provider, "status": "unknown"}

        usage = self.usage[provider]
        limit = self.limits[provider]

        return {
            "provider": provider,
            "requests_today": usage.requests_today,
            "requests_today_limit": limit.requests_per_day,
            "requests_today_utilization": usage.requests_today / limit.requests_per_day,
            "requests_this_minute": usage.requests_this_minute,
            "requests_this_minute_limit": limit.requests_per_minute,
            "requests_this_minute_utilization": usage.requests_this_minute / limit.requests_per_minute,
            "concurrent_requests": usage.concurrent_requests,
            "max_concurrent": limit.max_concurrent,
            "last_call": usage.call_history[-1] if usage.call_history else None,
        }


class APIKeyGatingService:
    """
    PHASE 3: Orchestrates API key validation, rate limiting, and quota management.
    
    This is the gate through which all external API calls must pass.
    Responsibilities:
    1. Validate API key exists and is configured
    2. Check rate limits
    3. Check quota
    4. Record successful calls
    5. Track provider health
    
    Usage:
        gating = APIKeyGatingService()
        can_call, reason = gating.check_can_call("google_places")
        if can_call:
            # Make external call
            response = await call_google_places(...)
            gating.record_success("google_places")
        else:
            # Fallback
            logger.warning(f"Cannot call google_places: {reason}")
    """

    def __init__(self):
        self.key_registry = APIKeyRegistry()
        self.rate_limiter = RateLimiter()
        self.quota_tracker = QuotaTracker()

    def check_can_call(self, provider: str) -> Tuple[bool, Optional[str]]:
        """
        PHASE 3 GATE: Check if external call can be made.
        
        Returns:
            (allowed, reason_if_denied)
        """
        # Gate 1: Is provider configured?
        if not self.key_registry.is_configured(provider):
            return False, f"Provider '{provider}' has no API key configured"

        # Gate 2: Rate limit check
        allowed, reason = self.rate_limiter.can_make_request(provider)
        if not allowed:
            logger.warning(f"Rate limit: {reason}")
            return False, reason

        # Gate 3: Quota check
        allowed, reason = self.quota_tracker.can_use_quota(provider)
        if not allowed:
            logger.warning(f"Quota limit: {reason}")
            return False, reason

        return True, None

    def record_call(self, provider: str, success: bool = True, error: str = None) -> None:
        """Record a call result for rate limiting and quota tracking."""
        self.rate_limiter.record_request(provider)
        self.quota_tracker.record_request(provider)

        if not success and error:
            self.key_registry.mark_key_error(provider, error)

    def get_provider_stats(self, provider: str) -> Dict[str, Any]:
        """Get comprehensive stats for a provider."""
        return {
            "provider": provider,
            "configured": self.key_registry.is_configured(provider),
            "rate_limiting": self.rate_limiter.get_stats(provider),
            "quota": self.quota_tracker.get_usage(provider),
            "key_status": self.key_registry.keys.get(provider, {}).get("status", "unknown"),
        }

    def get_all_stats(self) -> Dict[str, Any]:
        """Get stats for all configured providers."""
        return {
            "timestamp": datetime.now().isoformat(),
            "configured_providers": list(self.key_registry.list_configured().keys()),
            "providers": {
                provider: self.get_provider_stats(provider)
                for provider in self.key_registry.list_configured().keys()
            },
        }

    def __repr__(self) -> str:
        configured = list(self.key_registry.list_configured().keys())
        return f"APIKeyGatingService(configured_providers={len(configured)}, providers={configured})"


# Singleton instance
api_key_gating = APIKeyGatingService()
