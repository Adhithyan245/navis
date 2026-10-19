# PHASE 2: Response Schema Enforcement Implementation Guide

## Overview

Phase 2 implements comprehensive response schema enforcement across the entire FastAPI backend. Every response must conform to the unified `APIResponse` schema before leaving the system.

**Goal**: Guarantee deterministic, predictable, and safe response structure on all endpoints.

**Mandate**: "If ANY response violates the schema → system catches and normalizes it."

---

## Architecture

### Three-Layer Enforcement

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Stream Method Response Building                     │
│ - build_success_response()                                   │
│ - build_fallback_response()                                  │
│ - build_error_response()                                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: _finalize_stream() Validation                       │
│ - ResponseValidator.apply_to_stream_response()               │
│ - Ensures consistency before humanization                    │
│ - Never crashes; fallback to safe response                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Middleware Schema Enforcement                       │
│ - SchemaEnforcementMiddleware intercepts responses           │
│ - Final validation before HTTP serialization                 │
│ - Catches any schema violations escaping layers 1-2          │
└─────────────────────────────────────────────────────────────┘
```

---

## APIResponse Schema

All responses must conform to:

```python
class APIResponse(BaseModel):
    # Required
    status: Literal["success", "fallback", "error"]
    data: Union[List, Dict]  # Never None; always structure
    
    # Recommended
    sources: List[str] = []              # Which providers returned data
    source_mode: str = "fallback"        # "live", "cache", "hybrid", "fallback"
    explanation: str = ""                # User-friendly message
    
    # Optional metadata
    agent: str = "unknown"               # Endpoint/agent name
    source: str = "unknown"              # Primary data source
    message: str = None                  # Humanized message
    reason: str = None                   # Machine-readable reason
    suggestions: List[str] = None        # User suggestions
```

### Consistency Rules

1. **Status ↔ Source Mode**
   - If `status="fallback"` → must have `source_mode="fallback"`
   - If `status="success"` → must have sources and `source_mode="live"|"cache"|"hybrid"`

2. **Data Structure**
   - `data` must be dict or list (never None)
   - Empty dict `{}` is valid (means no results)
   - Empty list `[]` is valid (means no items)

3. **Sources Tracking**
   - `sources` list contains identifiers of data providers
   - Each source must be in `KNOWN_SOURCES` (warns if unknown, doesn't fail)
   - `sources` empty for fallback responses only

4. **Suggestions**
   - Only provided on fallback/error responses
   - Helps user recover or try alternatives

---

## Usage Patterns

### Pattern 1: Building Responses (Stream Methods)

```python
async def stream_explore(self, context: UserContext) -> AsyncGenerator[str, None]:
    # ... fetch data ...
    
    # Build response using schema-safe builders
    if results:
        final = self.build_success_response(
            data={"places": ranked_results},
            sources=["google_places"],
            source_mode="live",
            explanation=f"Found {len(ranked_results)} places.",
            agent="explore",
        )
    else:
        final = self.build_fallback_response(
            reason="No places found nearby.",
            db_sources=["saved_items_db"] if saved else [],
            suggestions=["Try a wider search radius", "Check Saved items"],
            agent="explore",
            data={"places": []},
        )
    
    # Validation happens in _finalize_stream
    yield await self._finalize_stream(final)
```

### Pattern 2: Direct Response Validation (Route Handlers)

```python
from core.schema_enforcement import validate_response_schema

@router.post("/search")
async def search_endpoint(query: str) -> APIResponse:
    try:
        results = await search_service.search(query)
        response = APIResponse(
            status="success" if results else "fallback",
            data={"results": results},
            sources=["search_provider"],
            source_mode="live" if results else "fallback",
            explanation="Search results",
            agent="search",
        )
    except Exception as e:
        response = ResponseValidator.error(
            reason=str(e),
            agent="search",
        )
    
    # Validate before returning
    return validate_response_schema(response, context="search")
```

### Pattern 3: Merging Multiple Responses

```python
from services.response_validator import response_validator

responses = [
    await get_google_places_results(),
    await get_yelp_results(),
    await get_local_db_results(),
]

# Merge with best-quality strategy
merged = response_validator.merge_responses(
    responses,
    merge_strategy="best",
    context="taste_endpoint",
)

yield await self._finalize_stream(merged)
```

### Pattern 4: Middleware Enforcement on Routes

```python
from core.schema_enforcement import enforce_schema

@router.get("/explore")
@enforce_schema("explore")  # Automatic validation wrapper
async def get_explore(context: UserContext) -> APIResponse:
    # Your endpoint logic
    return response
```

---

## Core Components

### 1. ResponseValidator Service

**Location**: `services/response_validator.py`

**Key Methods**:

- `validate(response, context)` - Validate dict/APIResponse to schema
- `ensure_consistency(response)` - Fix minor schema issues
- `apply_to_stream_response(response, domain, context)` - Full validation pipeline

**Response Builders**:

- `success()` - Build success response
- `fallback()` - Build fallback response  
- `error()` - Build error response
- `from_provider_response()` - Normalize ProviderManager output
- `merge_responses()` - Combine multiple responses

**Inspection**:

- `is_valid(response)` - Check if response valid
- `get_issues(response)` - List schema issues
- `log_issues(response, context)` - Log warnings

### 2. Schema Enforcement Middleware

**Location**: `core/schema_enforcement.py`

**Components**:

- `SchemaEnforcementMiddleware` - ASGI middleware for global enforcement
- `@enforce_schema(endpoint_name)` - Decorator for individual handlers
- `validate_response_schema(response, context)` - Standalone validation function

**Behavior**:

- Intercepts all 200/201 responses
- Validates APIResponse structure
- Normalizes if needed
- Returns safe fallback if invalid
- Never crashes; logs warnings

### 3. Orchestrator Helper Methods

**Location**: `agents/orchestrator.py`

**New Methods**:

- `build_success_response()` - Schema-safe success builder
- `build_fallback_response()` - Schema-safe fallback builder
- `build_error_response()` - Schema-safe error builder
- `_finalize_stream()` - Updated to enforce schema

---

## Integration Checklist

### For Stream Methods

- [ ] Replace manual `APIResponse()` calls with `self.build_*_response()` helpers
- [ ] Ensure all responses go through `yield await self._finalize_stream(final)`
- [ ] No direct `yield` of response without `_finalize_stream()`
- [ ] All success responses include `sources` list
- [ ] All fallback responses include `suggestions`

### For Route Handlers

- [ ] Import `from core.schema_enforcement import enforce_schema, validate_response_schema`
- [ ] Use `@enforce_schema("endpoint_name")` decorator on endpoint
- [ ] Or wrap final response with `validate_response_schema(response, context="endpoint")`
- [ ] Return type annotation should be `-> APIResponse`

### For Main Application

- [ ] Register `SchemaEnforcementMiddleware` in FastAPI app init
- [ ] Add middleware early in chain (before other middleware if possible)
- [ ] Verify middleware doesn't conflict with stream responses

### Example Middleware Registration

```python
from fastapi import FastAPI
from core.schema_enforcement import SchemaEnforcementMiddleware

app = FastAPI()

# Register middleware (runs in reverse order)
app.add_middleware(SchemaEnforcementMiddleware)

# ... rest of app setup ...
```

---

## Validation Flow

### When Response is Created

```
build_success_response()
    ↓
APIResponse(**kwargs)  [Pydantic validates basic types]
    ↓
Returns: APIResponse instance
```

### When Response is Finalized (_finalize_stream)

```
_finalize_stream(response)
    ↓
ResponseValidator.apply_to_stream_response()
    ├─ validate(response, context)         [Pydantic re-validate]
    ├─ ensure_consistency(response)        [Fix minor issues]
    └─ log_issues(response, context)       [Warn on problems]
    ↓
response.model_dump()  [Serialize to dict]
    ↓
yield NDJSON event
```

### When Response Exits (Middleware)

```
HTTP Response (200/201)
    ↓
SchemaEnforcementMiddleware.dispatch()
    ├─ Extract JSON body
    ├─ ResponseValidator.validate()
    ├─ If invalid → return safe fallback
    └─ If valid → pass through
    ↓
HTTP response to client
```

---

## Error Handling

### What Happens if Schema Validation Fails?

1. **In _finalize_stream**: Catches exception, logs error, returns safe fallback
   ```python
   try:
       response = response_validator.apply_to_stream_response(...)
   except ResponseValidationError:
       response = response_validator.fallback(reason="Validation failed")
   ```

2. **In Middleware**: Logs error, returns safe fallback response
   ```python
   except ResponseValidationError as e:
       fallback = ResponseValidator.fallback(...)
       return JSONResponse(fallback.model_dump(), status_code=200)
   ```

3. **User Experience**: Never crashes; always gets 200 with fallback data

### Common Issues and Fixes

| Issue | Fix |
|-------|-----|
| `data=None` | Use `data={}` or `data=[]` |
| `sources=None` | Use `sources=[]` |
| `status="fallback"` but `source_mode="live"` | Set `source_mode="fallback"` |
| Unknown source identifier | Add to `KNOWN_SOURCES` in response.py |
| Empty data with success status | Use status="fallback" instead |
| `source_mode=None` when status="success" | Set to "live" or "cache" |

---

## Testing Phase 2

### Unit Tests

```python
from services.response_validator import ResponseValidator, ResponseValidationError

def test_validate_success_response():
    response = APIResponse(
        status="success",
        data={"places": [...]},
        sources=["google_places"],
        source_mode="live",
    )
    validated = ResponseValidator.validate(response, context="test")
    assert validated.status == "success"
    assert "google_places" in validated.sources

def test_fallback_has_suggestions():
    response = ResponseValidator.fallback(
        reason="No data",
        suggestions=["Try again", "Search elsewhere"],
    )
    assert response.status == "fallback"
    assert len(response.suggestions) >= 2
    assert response.source_mode == "fallback"

def test_inconsistency_fixed():
    response = APIResponse(
        status="fallback",
        data={},
        source_mode="live",  # WRONG!
    )
    fixed = ResponseValidator.ensure_consistency(response)
    assert fixed.source_mode == "fallback"
```

### Integration Tests

```python
def test_stream_response_validated():
    # Run a stream endpoint
    response = orchestrator.stream_explore(context)
    
    # Check all fields
    assert response.status in ("success", "fallback", "error")
    assert isinstance(response.data, (dict, list))
    assert isinstance(response.sources, list)
    assert response.source_mode in ("live", "cache", "hybrid", "fallback")
```

---

## Monitoring Phase 2

### Metrics to Track

1. **Schema Validation Rate**
   - How many responses pass validation on first try
   - Target: > 99%

2. **Consistency Fixes Applied**
   - How many responses needed fixing
   - Target: < 1%

3. **Fallback Rate**
   - How many responses are fallback vs. success
   - Use to detect provider issues

4. **Source Distribution**
   - Which providers provide most data
   - Track provider health

### Logging to Watch

```
WARNING: Schema issues in stream_explore:
  - Empty data dict with success status

WARNING: Correcting source_mode to 'fallback' (was 'live')

ERROR: Response validation failed in explore: Invalid status 'pending'

INFO: Unknown source identifier 'new_provider_xyz'
```

---

## Phase 2 Compliance Checklist

- [ ] ResponseValidator service created and tested
- [ ] SchemaEnforcementMiddleware created and registered
- [ ] Orchestrator updated with builder methods
- [ ] _finalize_stream updated to enforce schema
- [ ] All stream methods use builders or validate responses
- [ ] All route handlers use @enforce_schema or validate_response_schema
- [ ] Middleware registered in main FastAPI app
- [ ] No responses bypass validation layers
- [ ] All test routes pass schema validation
- [ ] Monitoring/logging in place for schema issues

---

## Next: Phase 3

Once Phase 2 is 100% complete and validated, move to **Phase 3: API Key Gating**.

See ADAPTIVE_INTELLIGENCE_IMPLEMENTATION.md for full Phase 3-8 roadmap.
