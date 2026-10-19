# ADAPTIVE INTELLIGENCE IMPLEMENTATION — CODE TRUTH VERIFICATION

**Date**: April 21, 2026  
**Report**: Actual code inspection against implementation claims

---

## 1. DB Model File Path ✅

**ACTUAL TRUTH**: `apps/api/models/db_models.py`

**Location**: Lines 82-130

```python
class UserInteraction(Base):
    """Tracks real user behavior: clicks, saves, views, rsvps, queries."""
    __tablename__ = "user_interactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    item_id = Column(String, nullable=True)
    item_type = Column(String, nullable=True)
    action_type = Column(String, nullable=False)
    domain = Column(String, nullable=True)
    city = Column(String, nullable=True)
    query = Column(String, nullable=True)
    item_categories = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ContextMemory(Base):
    """Persists recent user context for adaptive suggestions and ranking."""
    __tablename__ = "context_memory"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True, nullable=False)
    recent_searches = Column(JSON, default=list)
    recent_domains = Column(JSON, default=list)
    recent_locations = Column(JSON, default=list)
    category_affinities = Column(JSON, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

---

## 2. Behavior Tracking Blocking Analysis ❌ LATENCY RISK

**CLAIM**: "Non-blocking, fire-and-forget"  
**ACTUAL TRUTH**: INLINE AWAITS without outer exception handling

### File: `apps/api/agents/orchestrator.py`

**Stream Explore** (Lines 63-102):
```python
async def stream_explore(self, context: UserContext) -> AsyncGenerator[str, None]:
    yield await self._yield_event("understanding_request", 10)

    # Record query interaction
    user_id = int(context.user_id) if context.user_id.isdigit() else -1
    if user_id > 0:
        q = " ".join(context.preferences) if context.preferences else "points of interest"
        await self.behavior_tracker.record_query(user_id, "explore", context.new_city, q)
        # ↑ AWAITED INLINE ↑ NO TRY-EXCEPT WRAPPER
```

**Stream Work** (Lines 120-148):
```python
    # Record query interaction
    user_id = int(context.user_id) if context.user_id.isdigit() else -1
    if user_id > 0:
        await self.behavior_tracker.record_query(user_id, "work", context.new_city, f"work {context.work_style or ''}")
        # ↑ AWAITED INLINE ↑ NO TRY-EXCEPT WRAPPER
```

**Stream Services** (Lines 152-155):
```python
    # Record query interaction
    user_id = int(context.user_id) if context.user_id.isdigit() else -1
    if user_id > 0:
        await self.behavior_tracker.record_query(user_id, "services", context.new_city, " ".join(context.preferences or ["hospital"]))
        # ↑ AWAITED INLINE ↑ NO TRY-EXCEPT WRAPPER
```

**Stream Events** (Lines 234-237):
```python
    # Record query interaction
    user_id = int(context.user_id) if context.user_id.isdigit() else -1
    if user_id > 0:
        await self.behavior_tracker.record_query(user_id, "connect", context.new_city, " ".join(...))
        # ↑ AWAITED INLINE ↑ NO TRY-EXCEPT WRAPPER
```

**Stream Explore** (Lines 82-86):
```python
        # Get adaptive weights from behavior
        behavior_weights = {}
        ignored_cats = []
        if user_id > 0:
            behavior_weights = await self.behavior_tracker.compute_adaptive_weights(user_id)
            ignored_cats = await self.behavior_tracker.get_ignored_categories(user_id)
            # ↑ AWAITED INLINE ↑ NO TRY-EXCEPT WRAPPER
```

**Blocking Analysis**:

| Call | Location | Blocking | Exception Handler |
|------|----------|----------|-------------------|
| `record_query()` | Line 71 | **YES** (await) | **NO** outer wrapper |
| `compute_adaptive_weights()` | Line 84 | **YES** (await) | **NO** outer wrapper |
| `get_ignored_categories()` | Line 85 | **YES** (await) | **NO** outer wrapper |
| `record_query()` | Line 133 | **YES** (await) | **NO** outer wrapper |
| `record_query()` | Line 156 | **YES** (await) | **NO** outer wrapper |
| `record_query()` | Line 237 | **YES** (await) | **NO** outer wrapper |

**Exception Path Analysis**:

```
orchestrator.stream_explore()
  → await behavior_tracker.record_query()
      → await self.record() [HAS try-except] ✅
           → asyncSession.commit()
  
orchestrator.stream_explore()
  → await behavior_tracker.compute_adaptive_weights()
      → await self.get_category_affinities() [HAS try-except] ✅
           → asyncSession.execute()
      → NO OUTER TRY-EXCEPT AT METHOD LEVEL ❌

IF get_category_affinities() somehow raises OUTSIDE try block:
  Exception propagates → orchestrator.stream_explore() crashes
  → Stream terminates
  → Client receives incomplete response
```

**Actual Exception Handling**:

File: `apps/api/services/behavior.py`

```python
async def record(self, user_id: int, action_type: str, ...):
    """Record a single user interaction."""
    try:
        async with AsyncSessionLocal() as session:
            session.add(UserInteraction(...))
            await session.commit()
    except Exception:
        pass  # ✅ INNER EXCEPTION CAUGHT

async def record_query(self, user_id: int, domain: str, city: str, query: str):
    await self.record(...)  # ✅ Exception caught inside record()

async def get_category_affinities(self, user_id: int, limit: int = 50):
    try:
        async with AsyncSessionLocal() as session:
            # DB queries...
    except Exception:
        pass
    return dict(affinities)

async def compute_adaptive_weights(self, user_id: int) -> Dict[str, float]:
    affinities = await self.get_category_affinities(user_id)  # ✅ Catches exceptions
    if not affinities:
        return {}
    # ... no outer try-except
    max_count = max(affinities.values())  # ✅ Could raise if affinities is malformed
    # ...
```

**RISK ASSESSMENT**:

- ✅ `record_query()` → safe, exception caught in `record()`
- ✅ `record_click()` → safe, exception caught in `record()`
- ✅ `record_save()` → safe, exception caught in `record()`
- ⚠️ `compute_adaptive_weights()` → depends on `get_category_affinities()` safely returning empty dict
- ⚠️ `get_ignored_categories()` → same risk
- ⚠️ `compute_save_boost()` → has try-except, safe

**VERDICT**: Behavior can add latency while awaiting. If orchestrator is handling 10 concurrent requests, all must wait for DB queries to finish. No background task processing.

---

## 3. API Response Payload: Rationale Exposure ✅ INTENTIONAL

**CLAIM**: "Rationale field not exposed to clients"  
**ACTUAL TRUTH**: RATIONALE IS KEPT AND SENT TO CLIENTS

**File**: `apps/api/services/ranking.py` (Lines 176-185)

```python
# Build ranking rationale using ONLY real fields
rationale = {}
if rating > 0:
    rationale["rating"] = rating
if distance_km is not None:
    rationale["distance_km"] = round(distance_km, 2)
if price_level is not None:
    rationale["price_level"] = price_level
if p.get("open_now") is not None:
    rationale["open_now"] = p["open_now"]
if is_saved:
    rationale["saved"] = True
if behavior_boost > 0:
    rationale["behavior_affinity_boost"] = round(behavior_boost, 2)

p["_rank"] = {"score": round(score, 2), "idx": idx}
p["rationale"] = rationale  # Human-meaningful, safe to send to frontend
```

**Strip Metadata Function** (Line 299):
```python
@staticmethod
def strip_ranking_metadata(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove internal _rank keys before sending to client. Keep rationale."""
    for item in items:
        item.pop("_rank", None)
        item.pop("_ranking_score", None)
    return items
```

**What is REMOVED**: `_rank`, `_ranking_score`  
**What is KEPT**: `rationale` (includes behavior_affinity_boost)

**Orchestrator Calls** (9 locations):
```
Line 96:  RankingService.strip_ranking_metadata(ranked)  # explore
Line 148: RankingService.strip_ranking_metadata(ranked)  # work
Line 205: RankingService.strip_ranking_metadata(services_data)  # services
Line 278: RankingService.strip_ranking_metadata(ranked)  # connect
Line 467: RankingService.strip_ranking_metadata(ranked)  # work (alternate)
Line 488: RankingService.strip_ranking_metadata(pharmacies)  # services (alternate)
Line 509: RankingService.strip_ranking_metadata(ranked)  # ? (alternate)
Line 528: RankingService.strip_ranking_metadata(clinics)  # services (alternate)
```

**Routes Returning Rationale**:
1. `/explore` — places with rationale
2. `/work` — places with rationale
3. `/services` — services with rationale
4. `/connect` — events with rationale
5. `POST /onboard` — no rationale (user profile creation)

**Example Response**:
```json
{
  "status": "success",
  "data": {
    "places": [
      {
        "place_id": "ChIJ1...",
        "name": "Brew Haven",
        "rating": 4.5,
        "location": {"lat": 42.3, "lng": -71.06},
        "rationale": {
          "rating": 4.5,
          "distance_km": 0.8,
          "open_now": true,
          "saved": false,
          "behavior_affinity_boost": 2.5
        }
      }
    ]
  }
}
```

**VERDICT**: ✅ Intentional. Rationale IS exposed. Includes `behavior_affinity_boost` transparently.

---

## 4. Write Boundaries: User State Mutation ✅ MOSTLY CLEAN

**Question**: Which files/routes write persistent user state?

### UserProfile Writes

**File**: `apps/api/routes/onboard.py` (Lines 9-23)

```python
@router.post("", response_model=APIResponse)
async def onboard_user(context: UserContext):
    try:
        async with AsyncSessionLocal() as session:
            profile = UserProfile(
                user_id=int(context.user_id) if context.user_id.isdigit() else None,
                old_city=context.old_city,
                new_city=context.new_city,
                preferences=context.preferences,
                dislikes=context.dislikes,
                home_anchor=context.home_anchor,
                work_anchor=context.work_anchor,
            )
            session.add(profile)
            await session.commit()
            db_sources.append("user_profiles_db")
    except Exception:
        pass  # DB may not be initialized; context is still usable in-memory
```

**UserProfile Writes**: 
- ✅ **Only**: `/onboard` route
- ✅ **When**: User explicitly calls onboard
- ✅ **NOT mutated by**: search flows (explore, work, connect, services, move, settle)

### ContextMemory Writes

**File**: `apps/api/services/behavior.py` (Lines 212-251)

```python
class ContextMemoryService:
    async def update_memory(self, user_id: int, search_entry, domain, location, category_affinities):
        try:
            async with AsyncSessionLocal() as session:
                # Update ContextMemory table
                ...
        except Exception:
            pass
```

**ContextMemory Writes**:
- ❌ **NEVER CALLED** anywhere in codebase
- ❌ Method exists but is unused
- ❌ No search flow calls `context_memory.update_memory()`

### UserInteraction Writes

**File**: `apps/api/services/behavior.py` (Lines 24-47)

```python
async def record_query(self, user_id: int, domain: str, city: str, query: str):
    await self.record(user_id, "query", domain=domain, city=city, query=query)

async def record_click(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
    await self.record(user_id, "click", item_id=item_id, item_type=item_type, ...)

async def record_save(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
    await self.record(user_id, "save", item_id=item_id, item_type=item_type, ...)
```

**UserInteraction Writes**: 
- ✅ Called in: explore, work, services, connect
- ✅ Only writes: queries (no persist of user preferences)
- ✅ NOT called for: clicks/saves (nowhere in orchestrator)
- ✅ Side-effect: records to UserInteraction table

**VERDICT**: 
- ✅ UserProfile: only written by `/onboard`
- ⚠️ ContextMemory: defined but never written (dead code)
- ⚠️ UserInteraction: written by search flows, but ONLY queries, NOT clicks/saves

---

## 5. Adaptive Ranking Bounds ✅ WELL DEFINED

**File**: `apps/api/services/ranking.py`

### Max Behavior Boost

**Per-category boost**: 0.0 to 5.0

```python
async def compute_adaptive_weights(self, user_id: int) -> Dict[str, float]:
    affinities = await self.get_category_affinities(user_id)
    max_count = max(affinities.values())
    for cat, count in affinities.items():
        # Normalize to 0-5 range
        weights[cat] = round((count / max_count) * 5.0, 2)
    return weights
```

**Applied in ranking** (Line 171):
```python
behavior_boost = 0.0
for cat_type in types_lower:
    if cat_type in behavior_weights:
        behavior_boost += behavior_weights[cat_type]

if behavior_boost > 0:
    score += behavior_boost
```

**Total per-place**: Could accumulate if place has multiple matching types
- Example: place with types ["cafe", "restaurant"] where user boosted both:
- `behavior_boost = 5.0 + 5.0 = 10.0` (accumulates!)

### Max Ignored Penalty

**Per-category penalty**: -0.5 only

```python
ignored_penalty = 0.0
for cat_type in types_lower:
    if cat_type in ignored_categories:
        ignored_penalty -= 0.5

score += ignored_penalty
```

**Total per-place**: -0.5 per ignored category matched

### Default Behavior for New Users

```python
if behavior_weights is None:
    behavior_weights = {}
if ignored_categories is None:
    ignored_categories = []
```

**New users get**: 
- `behavior_weights = {}` → no boost
- `ignored_categories = []` → no penalty
- **Score = original ranking** ✅

### Fallback on DB Failure

**File**: `apps/api/services/behavior.py`

```python
async def compute_adaptive_weights(self, user_id: int):
    affinities = await self.get_category_affinities(user_id)
    # If DB fails, get_category_affinities returns {} (caught exception)
    if not affinities:
        return {}  # ✅ Returns empty dict
```

```python
async def get_ignored_categories(self, user_id: int):
    try:
        # DB query
    except Exception:
        pass
    return []  # ✅ Returns empty list
```

**Fallback behavior**: Returns empty weights/categories → no ranking effect

**VERDICT**: ✅ All bounds well-defined and safe

---

## 6. Summary of Code-Truth Findings

| Item | Claim | Actual Code | Status |
|------|-------|------------|--------|
| DB Path | `apps/api/models/db_models.py` | ✅ Correct | ✓ |
| Blocking | "Non-blocking" | Inline awaits without outer try-except | ⚠️ Latency Risk |
| Rationale Exposure | "Not exposed" | `strip_ranking_metadata()` keeps it; sent in responses | ✅ Intentional |
| UserProfile Writes | "Only from onboard" | Confirmed only `/onboard` route | ✓ |
| ContextMemory Writes | "Updated per request" | Method exists but **NEVER CALLED** | ❌ Dead Code |
| UserInteraction | "Logs clicks/saves" | Only queries logged, not clicks/saves | ⚠️ Incomplete |
| Behavior Boost | "0-5 per category" | Correct, but accumulates across types | ✓ |
| Ignored Penalty | "-0.5 per category" | Correct | ✓ |
| New Users | "Default to original ranking" | Yes, empty weights/categories | ✓ |
| DB Failure | "Fallback to empty" | Yes, returns {} or [] | ✓ |

---

## Critical Discrepancies

### 1. ❌ Behavior Tracking Latency

**Implementation claims non-blocking**, but orchestrator does:
```python
await self.behavior_tracker.record_query(...)  # Blocks until DB completes
await self.behavior_tracker.compute_adaptive_weights(...)  # Blocks until DB completes
```

These are inline awaits that **WILL add latency** to the response stream.

### 2. ❌ ContextMemory Never Updated

Method `update_memory()` exists but is never called anywhere. **Dead code**.

Implication: `recent_searches`, `recent_domains`, `recent_locations` are never persisted.

### 3. ⚠️ Click/Save Interactions Not Logged

Orchestrator only logs queries:
```python
await self.behavior_tracker.record_query(...)
```

**Not called for**:
- Clicks on items
- Saves of items

Claims said "log clicks, saves, views" but only queries are actually logged.

### 4. ✅ Rationale IS Exposed

`strip_ranking_metadata()` only removes `_rank` and `_ranking_score`, but keeps `rationale` including `behavior_affinity_boost`.

This is intentional and correct, but the documentation said "not exposed."

---

## Exact File Paths and Code Snippets

**DB Models**: `d:\olaa-native\apps\api\models\db_models.py` (Lines 82-130)

**Orchestrator Blocking Calls**: `d:\olaa-native\apps\api\agents\orchestrator.py`
- Line 71: `await self.behavior_tracker.record_query(...)`
- Line 84-85: `await self.behavior_tracker.compute_adaptive_weights(...)`
- Line 133: `await self.behavior_tracker.record_query(...)`
- Line 156: `await self.behavior_tracker.record_query(...)`
- Line 237: `await self.behavior_tracker.record_query(...)`

**Ranking Rationale**: `d:\olaa-native\apps\api\services\ranking.py` (Lines 176-185)

**Strip Metadata**: `d:\olaa-native\apps\api\services\ranking.py` (Lines 298-302)

**UserProfile Writes**: `d:\olaa-native\apps\api\routes\onboard.py` (Lines 9-23)

**ContextMemory Service**: `d:\olaa-native\apps\api\services\behavior.py` (Lines 209-289) — **Never called**

---

## Conclusion

All code truth has been extracted. The implementation has:
- ✅ Correct DB schema paths
- ⚠️ **Latency risk** from inline behavior tracking awaits
- ✅ Intentional rationale exposure to clients
- ✓ Clean UserProfile write boundaries
- ❌ Dead code: ContextMemory.update_memory()
- ⚠️ Incomplete interaction logging (queries only, not clicks/saves)
