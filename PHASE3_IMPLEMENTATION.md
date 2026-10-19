# PHASE 3: API Key Gating & Quota Management Implementation Guide

## Overview

Phase 3 implements comprehensive **API key validation, rate limiting, and quota tracking** across all external provider calls. This is the critical security and reliability layer that prevents unauthorized calls, protects against rate limit violations, and ensures predictable resource consumption.

**Goal**: Enforce authentication and authorization before ANY external API call is made.

**Mandate**: "Only authorized calls reach external providers."

---

## Architecture

### API Key Gating System

```
ProviderManager
    ↓
[REQUEST COMES IN]
    ↓
_check_gate(provider) ───┐
    ├─ APIKeyRegistry:   │
    │  "Is provider      │
    │   configured?"     │
    │                    ├─→ (allowed, reason)
    ├─ RateLimiter:      │
    │  "Rate limit OK?"  │
    │                    │
    └─ QuotaTracker:     │
       "Quota OK?"       │
    ↑                    │
    └─────────────────────┘

    If allowed → Make external call + record_call()
    If denied  → Return fallback response
```

### Four Core Components

#### 1. **APIKeyRegistry** 
   - Maintains configured API keys from environment
   - Tracks key status (active, error, disabled)
   - Supports per-provider key configuration

#### 2. **RateLimiter**
   - Per-provider call rate limiting (calls/second, calls/minute)
   - Non-blocking checks; doesn't queue requests
   - Resets counters on time boundaries

#### 3. **QuotaTracker**
   - Per-provider daily quota limits
   - Per-provider per-minute quotas
   - Concurrent request tracking
   - Call history for debugging

#### 4. **APIKeyGatingService**
   - Orchestrates all three components
   - Single gate through which all external calls pass
   - Returns permission + reason if denied
   - Records successful/failed calls for metrics

---

## API Key Configuration

### Supported Providers

| Provider | Env Variable | Default Limit | Notes |
|----------|--------------|---------------|-------|
| google_places | GOOGLE_PLACES_API_KEY | 25,000/day | Highest free tier |
| yelp | YELP_API_KEY | 5,000/day | Requires key |
| eventbrite | EVENTBRITE_API_KEY | 5,000/day | Optional |
| ticketmaster | TICKETMASTER_API_KEY | 5,000/day | Optional |
| mbta | MBTA_API_KEY | 50,000/day | High rate |
| adzuna | ADZUNA_APP_ID + ADZUNA_APP_KEY | 5,000/day | Two keys |

### Setup Instructions

```bash
# Set in your .env file
export GOOGLE_PLACES_API_KEY="AIzaSyD..."
export YELP_API_KEY="eyJhbGci..."
export EVENTBRITE_API_KEY="..."
export MBTA_API_KEY="..."

# Verify configuration on startup
# ProviderManager logs: "APIKeyGatingService(configured_providers=4, providers=[...])"
```

---

## Rate Limiting

### Per-Provider Limits

```python
limits = {
    "google_places": {"per_second": 10, "per_minute": 100},
    "yelp": {"per_second": 5, "per_minute": 50},
    "eventbrite": {"per_second": 5, "per_minute": 50},
    "ticketmaster": {"per_second": 5, "per_minute": 50},
    "mbta": {"per_second": 20, "per_minute": 200},
    "wikipedia": {"per_second": 10, "per_minute": 100},
    "osm": {"per_second": 10, "per_minute": 100},
}
```

### Rate Limit Behavior

- **Non-blocking**: Requests exceeding limits are rejected immediately (no queue)
- **Second-level tracking**: Resets call history every second
- **Minute-level tracking**: Maintains history for 60 seconds
- **Per-provider**: Each provider has independent limits
- **Global not isolated**: All calls to a provider count toward limit

### Example Flow

```
REQUEST 1: google_places (9/10 per-second OK) → ALLOW ✓
REQUEST 2: google_places (10/10 per-second OK) → ALLOW ✓
REQUEST 3: google_places (11/10 per-second) → DENY ✗
           "Rate limit: 10 calls/second for google_places"

[1 second passes]

REQUEST 4: google_places (1/10 per-second OK) → ALLOW ✓
```

---

## Quota Tracking

### Daily Quotas

Tracks requests per calendar day (resets at midnight):

```python
quotas = {
    "google_places": 25000,      # Highest free tier
    "yelp": 5000,
    "eventbrite": 5000,
    "ticketmaster": 5000,
    "mbta": 50000,
    "wikipedia": 100000,
    "osm": 50000,
}
```

### Per-Minute Quotas

Also enforces per-minute limits to prevent bursts:

```python
per_minute_limits = {
    "google_places": 100,
    "yelp": 60,
    "eventbrite": 60,
    "mbta": 1000,
}
```

### Concurrent Request Limits

Tracks how many requests are "in flight" to prevent overwhelming provider:

```python
max_concurrent = {
    "google_places": 10,
    "yelp": 10,
    "mbta": 50,
}
```

### Quota Tracking Example

```
DAY 1 - REQUEST 1: search_places() → ALLOW (1/25000) ✓
DAY 1 - REQUEST 2: search_places() → ALLOW (2/25000) ✓
...
DAY 1 - REQUEST 25000: search_places() → ALLOW (25000/25000) ✓
DAY 1 - REQUEST 25001: search_places() → DENY ✗
        "Daily quota exhausted: 25000 requests/day for google_places"

[Midnight]

DAY 2 - REQUEST 1: search_places() → ALLOW (1/25000) ✓  [Reset!]
```

---

## Integration with ProviderManager

### Updated Method Signature

All ProviderManager methods now include gating:

```python
async def search_places(
    self,
    query: str,
    lat: float,
    lng: float,
    radius: int = 1000,
    limit: int = 20,
) -> Dict[str, Any]:
    # Step 1: Check gate
    allowed, gate_reason = self._check_gate("google_places")
    if not allowed:
        logger.info(f"Places search gated: {gate_reason}")
        return {"results": [], "source": "fallback", "error": gate_reason}
    
    # Step 2: Make external call
    result = await places_provider.search(query, lat, lng, radius, limit)
    
    # Step 3: Record result
    if result.get("source") == "google_places":
        self._record_gate_result("google_places", success=True)
    
    return result
```

### Three-Step Pattern (Used in All Methods)

1. **Check Gate**: `allowed, reason = self._check_gate(provider)`
2. **Call or Fallback**: If allowed → call provider, else → return fallback
3. **Record Result**: `self._record_gate_result(provider, success=True/False)`

---

## Gating Status Monitoring

### Get Overall Status

```python
from services.provider_manager import ProviderManager

pm = ProviderManager()
stats = pm.get_gating_status()

print(stats)
# {
#     "timestamp": "2026-05-13T10:23:45.123456",
#     "configured_providers": ["google_places", "yelp", "mbta"],
#     "providers": {
#         "google_places": {
#             "provider": "google_places",
#             "configured": True,
#             "rate_limiting": {
#                 "calls_this_second": 3,
#                 "limit_per_second": 10,
#                 "calls_this_minute": 45,
#                 "limit_per_minute": 100,
#                 "utilization_second": 0.30,
#                 "utilization_minute": 0.45,
#             },
#             "quota": {
#                 "requests_today": 1234,
#                 "requests_today_limit": 25000,
#                 "requests_today_utilization": 0.049,  # 4.9%
#                 ...
#             },
#             "key_status": "active",
#         },
#         ...
#     }
# }
```

### Get Provider-Specific Stats

```python
stats = pm.get_provider_gating_stats("google_places")

print(stats["rate_limiting"])
# {
#     "calls_this_second": 3,
#     "limit_per_second": 10,
#     "utilization_second": 0.30,
# }

print(stats["quota"])
# {
#     "requests_today": 1234,
#     "requests_today_utilization": 0.049,
#     "last_call": {
#         "timestamp": "2026-05-13T10:23:44.567890",
#         "provider": "google_places"
#     }
# }
```

---

## Error Handling

### When Gating Denies Call

**Reason Format**: `"[TYPE]: [DETAIL] for [PROVIDER]"`

Examples:
- `"Rate limit: 10 calls/second for google_places"`
- `"Daily quota exhausted: 25000 requests/day for google_places"`
- `"Per-minute quota exhausted: 100 requests/minute for google_places"`
- `"Provider 'google_places' has no API key configured"`
- `"Max concurrent requests reached: 10 for google_places"`

### Response When Gated

```python
# Before gating:
response = await pm.search_places("coffee", 42.36, -71.06)
# If gated:
response = {
    "results": [],
    "source": "fallback",
    "error": "Rate limit: 10 calls/second for google_places"
}
```

### Logging

**Gate checks**: Logged at INFO level
```
INFO: Rate limit: 10 calls/second for google_places
INFO: Places search gated: Rate limit exceeded
```

**Key errors**: Logged at WARNING level
```
WARNING: Provider 'google_places' marked with error: "Invalid API key"
```

**Provider failures**: Logged at ERROR level
```
ERROR: ProviderManager.search_places failed: Connection timeout
```

---

## Testing Phase 3

### Unit Test: API Key Configuration

```python
from services.api_key_gating import APIKeyRegistry

def test_api_key_registry():
    registry = APIKeyRegistry()
    
    # Check configured providers
    assert registry.is_configured("google_places")
    assert not registry.is_configured("unknown_provider")
    
    # Get actual keys
    key = registry.get_key("google_places")
    assert key is not None
    assert len(key) > 10
    
    # Mark error
    registry.mark_key_error("google_places", "Invalid key format")
    assert registry.keys["google_places"]["status"] == "error"
```

### Unit Test: Rate Limiting

```python
from services.api_key_gating import RateLimiter

def test_rate_limiter():
    limiter = RateLimiter()
    
    # Initial requests should succeed
    for i in range(10):
        allowed, reason = limiter.can_make_request("google_places")
        assert allowed
        limiter.record_request("google_places")
    
    # 11th request should fail (limit is 10/second)
    allowed, reason = limiter.can_make_request("google_places")
    assert not allowed
    assert "Rate limit" in reason
```

### Unit Test: Quota Tracking

```python
from services.api_key_gating import QuotaTracker

def test_quota_tracker():
    tracker = QuotaTracker()
    
    # Record requests
    for i in range(1000):
        allowed, reason = tracker.can_use_quota("google_places")
        assert allowed
        tracker.record_request("google_places")
    
    # Check usage
    usage = tracker.get_usage("google_places")
    assert usage["requests_today"] == 1000
    assert usage["requests_today_utilization"] < 0.1  # 4% of 25000
```

### Integration Test: Gating Service

```python
from services.api_key_gating import api_key_gating

async def test_gating_service():
    # Initially should allow
    allowed, reason = api_key_gating.check_can_call("google_places")
    if api_key_gating.key_registry.is_configured("google_places"):
        assert allowed
    
    # Record call
    api_key_gating.record_call("google_places", success=True)
    
    # Get stats
    stats = api_key_gating.get_provider_stats("google_places")
    assert stats["configured"] is True
    assert stats["key_status"] == "active"
```

### Integration Test: ProviderManager Gating

```python
async def test_provider_manager_gating():
    pm = ProviderManager()
    
    # Search should work if configured
    result = await pm.search_places("coffee", 42.36, -71.06)
    
    # Should return either results or fallback
    assert isinstance(result, dict)
    assert result.get("source") in ("google_places", "fallback", "yelp")
    assert isinstance(result.get("results"), list)
```

---

## Monitoring & Alerting

### Metrics to Track

1. **Per-Provider Call Rate**
   - Current calls/second vs. limit
   - Alert if > 80% of second-level limit

2. **Daily Quota Utilization**
   - Current usage vs. daily limit
   - Alert if > 80% of daily limit

3. **Gating Denial Rate**
   - How many requests denied by gating
   - Alert if > 5% denial rate (indicates configuration issues)

4. **Provider Key Status**
   - Track providers marked with errors
   - Alert if any provider status changes to "error"

### Example Prometheus Metrics

```python
# In ProviderManager or metrics service
rate_limit_utilization = {
    "google_places": 0.35,  # 35% of per-second limit
    "yelp": 0.12,
    "mbta": 0.88,  # ALERT!
}

daily_quota_utilization = {
    "google_places": 0.042,  # 4.2% of daily limit
    "yelp": 0.201,
    "mbta": 0.95,  # ALERT!
}

gating_denial_rate = {
    "overall": 0.0023,  # 0.23% denied
}

key_status = {
    "google_places": "active",
    "yelp": "error",  # ALERT!
    "mbta": "active",
}
```

---

## Phase 3 Compliance Checklist

- [x] APIKeyRegistry created and tested
- [x] RateLimiter created and tested
- [x] QuotaTracker created and tested
- [x] APIKeyGatingService created and tested
- [x] ProviderManager.search_places updated with gating
- [x] ProviderManager.search_places_by_category updated with gating
- [x] ProviderManager.search_transit_routes updated with gating
- [x] ProviderManager.search_services updated with gating
- [x] ProviderManager.search_events updated with gating
- [x] ProviderManager.get_gating_status() added
- [x] ProviderManager.get_provider_gating_stats() added
- [ ] All other ProviderManager methods updated (pending)
- [ ] Route handlers consume gating stats via endpoint
- [ ] Monitoring dashboard displays gating metrics
- [ ] Alerting rules configured for quota/rate limit violations
- [ ] Runbook created for gating denial investigations

---

## Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| All requests denied with "no API key configured" | Environment variables not set | Set GOOGLE_PLACES_API_KEY etc. in .env |
| Rate limit errors despite low traffic | Multiple processes/instances competing | Add instance-aware rate limiting |
| Quota resets incorrectly | Timezone mismatch | Ensure server time is UTC |
| Calls succeed but gating shows "error" status | API key expired or revoked | Check provider dashboard; regenerate key |
| Memory leak in gating service | Call history not capped | Ensure call_history limited to 100 entries |

---

## Next: Phase 4

Once Phase 3 is validated in production:

**PHASE 4: Unified Response Schema Enforcement**
- Standardize all response structures
- Ensure consistent error reporting
- Implement response versioning

See ADAPTIVE_INTELLIGENCE_IMPLEMENTATION.md for full Phase 4-8 roadmap.

---

## Implementation Timeline

- **Hour 1**: Deploy APIKeyGatingService
- **Hour 2**: Update ProviderManager methods
- **Hour 3**: Add monitoring dashboard
- **Hour 4**: Test end-to-end with live traffic
- **Hour 5**: Deploy alerting rules
- **Hour 6**: Monitor metrics; handle incidents
- **Hour 24+**: Continuous optimization based on metrics

---

## Key Files

- `services/api_key_gating.py` - Core gating logic (600+ lines)
- `services/provider_manager.py` - Updated with gating integration (modified)
- This guide - Complete implementation reference

---

**PHASE 3 STATUS**: ✅ READY FOR DEPLOYMENT
