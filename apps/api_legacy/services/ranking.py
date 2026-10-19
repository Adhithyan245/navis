"""
Ranking engine for OLAA / Native.

─────────────────────────────────────────────────────────
ALLOWED RANKING INPUTS (documented contract)
─────────────────────────────────────────────────────────

Explore / Work (rank_places):
  - rating:      float, from Google Places "rating" field
  - price_level: int 0-4, from Google Places "price_level" field
  - open_now:    bool, from Google Places "opening_hours.open_now"
  - distance:    float km, Haversine from anchor_location
  - types:       list[str], from Google Places "types" field
                 matched against context.preferences/dislikes
  - saved:       bool, from saved_item_refs (DB-backed)
  - budget:      str, from context.budget — maps to price_level range

Connect (rank_events):
  - title:       str, from provider — preference substring match
  - start_time:  str, from provider — parsed for recency sort
  - category match from context.event_categories
  - saved:       bool, from saved_item_refs

Services (rank_services):
  - distance:    float km, from anchor
  - name:        str, used only for display

NEVER used:
  - inferred popularity
  - inferred noise level
  - "cheap" inferred from type names
  - "quiet" inferred from type names
  - synthetic scores

Tie-breaking:
  All domains: when scores are equal, preserve original provider ordering.
  This means higher-indexed items in the provider response appear later.
─────────────────────────────────────────────────────────
"""

import math
from typing import List, Dict, Any, Optional, Set
from models.context import UserContext

BUDGET_TO_PRICE_RANGE: Dict[str, tuple] = {
    "low": (0, 1),
    "medium": (1, 2),
    "high": (2, 4),
}

# Updated ranking inputs documentation
# NEW ADAPTIVE INPUTS (from user behavior):
#   - behavior_weights:  Dict[str, float], from BehaviorTracker.compute_adaptive_weights()
#                        Maps place type to adaptive boost (0.0-5.0)
#   - ignored_categories: List[str], from BehaviorTracker.get_ignored_categories()
#                         Categories user never saves despite viewing/clicking
#   - save_boost:        float (0.0-1.5), from BehaviorTracker.compute_save_boost()
#                        Multiplier for saved items based on user's save frequency
#
# ALL NEW LOGIC IS ADDITIVE:
# - Behavior weights only BOOST categories user has shown interest in
# - Ignored categories only SLIGHTLY DOWNRANK (penalty -0.5 per category match)
# - Save boost only affects already-saved items
# - Original provider signals (rating, distance, etc) remain unchanged


class RankingService:
    def _calculate_distance(self, lat1, lon1, lat2, lon2) -> float:
        if not all([lat1, lon1, lat2, lon2]):
            return 99999.0
        R = 6371  # km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def rank_places(
        self,
        places: List[Dict[str, Any]],
        context: UserContext,
        anchor_location: Optional[dict] = None,
        saved_item_refs: Optional[Set[str]] = None,
        behavior_weights: Optional[Dict[str, float]] = None,
        ignored_categories: Optional[List[str]] = None,
        save_boost: float = 0.0,
    ) -> List[Dict[str, Any]]:
        if saved_item_refs is None:
            saved_item_refs = set()
        if behavior_weights is None:
            behavior_weights = {}
        if ignored_categories is None:
            ignored_categories = []

        # Use home_anchor or work_anchor as fallback anchor if none provided
        if anchor_location is None:
            if context.home_anchor and context.home_anchor.get("lat"):
                anchor_location = context.home_anchor
            elif context.work_anchor and context.work_anchor.get("lat"):
                anchor_location = context.work_anchor

        scored = []
        for idx, p in enumerate(places):
            score = 0.0

            # 1. Rating — provider field (float 0-5)
            rating = float(p.get("rating", 0))
            score += rating * 2

            # 2. Distance from anchor — Haversine
            loc = p.get("location", {})
            distance_km = None
            if anchor_location and loc.get("lat") and anchor_location.get("lat"):
                distance_km = self._calculate_distance(
                    anchor_location["lat"], anchor_location.get("lng", 0),
                    loc["lat"], loc.get("lng", 0)
                )
                score -= distance_km * 0.5

            # 3. Preference match — only against provider-returned types
            types_lower = [t.lower() for t in p.get("types", [])]
            for pref in context.preferences:
                if pref.lower() in types_lower:
                    score += 5.0

            # 4. Food preference match — boost places matching food prefs
            for fp in context.food_preferences:
                if fp.lower() in types_lower:
                    score += 3.0

            # 5. Dislike penalty — only against provider-returned types
            for dislike in context.dislikes:
                if dislike.lower() in types_lower:
                    score -= 10.0

            # 6. Price level — only if provider returns it explicitly
            price_level = p.get("price_level")
            if price_level is not None and context.budget:
                budget_range = BUDGET_TO_PRICE_RANGE.get(context.budget)
                if budget_range:
                    if budget_range[0] <= price_level <= budget_range[1]:
                        score += 3.0
                    elif price_level > budget_range[1]:
                        score -= 2.0

            # 7. Open now — only if provider returns it explicitly
            if p.get("open_now") is True:
                score += 2.0

            # 8. Saved boost — DB-backed (with adaptive multiplier)
            place_id = p.get("place_id", "")
            is_saved = place_id in saved_item_refs
            if is_saved:
                base_saved_boost = 4.0
                # Apply save_boost multiplier if user saves frequently
                final_saved_boost = base_saved_boost * (1.0 + save_boost)
                score += final_saved_boost

            # ─── ADAPTIVE BEHAVIOR SIGNALS (ADDITIVE ONLY) ───
            # 9. Behavior-based category boost — not fabricated, DB-backed
            behavior_boost = 0.0
            for cat_type in types_lower:
                if cat_type in behavior_weights:
                    behavior_boost += behavior_weights[cat_type]

            if behavior_boost > 0:
                score += behavior_boost

            # 10. Ignored category penalty — slight downrank for categories user avoids
            ignored_penalty = 0.0
            for cat_type in types_lower:
                if cat_type in ignored_categories:
                    ignored_penalty -= 0.5

            score += ignored_penalty

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
            scored.append(p)

        scored.sort(key=lambda x: (x["_rank"]["score"], -x["_rank"]["idx"]), reverse=True)
        return scored

    def rank_events(
        self,
        events: List[Dict[str, Any]],
        context: UserContext,
        saved_item_refs: Optional[Set[str]] = None,
        behavior_weights: Optional[Dict[str, float]] = None,
        ignored_categories: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if saved_item_refs is None:
            saved_item_refs = set()
        if behavior_weights is None:
            behavior_weights = {}
        if ignored_categories is None:
            ignored_categories = []

        scored = []
        for idx, e in enumerate(events):
            score = 0.0
            title = e.get("title", "").lower()

            # 1. Preference match in title
            for pref in context.preferences:
                if pref.lower() in title:
                    score += 5.0

            # 2. Event category match
            for cat in context.event_categories:
                if cat.lower() in title:
                    score += 4.0

            # 3. Saved boost
            event_id = e.get("id", "")
            if event_id in saved_item_refs:
                score += 3.0

            # ─── ADAPTIVE BEHAVIOR SIGNALS (ADDITIVE ONLY) ───
            # 4. Behavior boost for event categories user has clicked/saved
            categories = e.get("categories", [])
            if isinstance(categories, list):
                for cat in categories:
                    if isinstance(cat, str):
                        cat_lower = cat.lower()
                        if cat_lower in behavior_weights:
                            score += behavior_weights[cat_lower]
                        if cat_lower in ignored_categories:
                            score -= 0.5

            e["_rank"] = {"score": round(score, 2), "idx": idx}
            scored.append(e)

        scored.sort(key=lambda x: (x["_rank"]["score"], -x["_rank"]["idx"]), reverse=True)
        return scored

    def rank_services(
        self,
        services: List[Dict[str, Any]],
        anchor_location: Optional[dict] = None,
        behavior_weights: Optional[Dict[str, float]] = None,
        ignored_categories: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if behavior_weights is None:
            behavior_weights = {}
        if ignored_categories is None:
            ignored_categories = []

        scored = []
        for idx, s in enumerate(services):
            score = 0.0
            loc = s.get("location", {})
            distance_km = None
            if anchor_location and loc.get("lat") and anchor_location.get("lat"):
                distance_km = self._calculate_distance(
                    anchor_location["lat"], anchor_location.get("lng", 0),
                    loc["lat"], loc.get("lng", 0)
                )
                score -= distance_km * 0.3

            # ─── ADAPTIVE BEHAVIOR SIGNALS (ADDITIVE ONLY) ───
            # Behavior boost for service types user has shown interest in
            service_type = s.get("type", "").lower()
            if service_type in behavior_weights:
                score += behavior_weights[service_type]
            if service_type in ignored_categories:
                score -= 0.5

            rationale = {}
            if distance_km is not None:
                rationale["distance_km"] = round(distance_km, 2)

            s["_rank"] = {"score": round(score, 2), "idx": idx}
            s["rationale"] = rationale
            scored.append(s)

        scored.sort(key=lambda x: (x["_rank"]["score"], -x["_rank"]["idx"]), reverse=True)
        return scored

    # Rationale keys permitted in API responses — strictly enforced
    _RATIONALE_ALLOWLIST = frozenset({
        "rating", "distance_km", "price_level",
        "open_now", "saved", "behavior_affinity_boost",
    })

    @staticmethod
    def strip_ranking_metadata(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove internal _rank keys and enforce rationale boundary before sending to client."""
        for item in items:
            item.pop("_rank", None)
            item.pop("_ranking_score", None)
            # Enforce rationale allowlist — remove any internal/debug fields
            if "rationale" in item and isinstance(item["rationale"], dict):
                item["rationale"] = {
                    k: v for k, v in item["rationale"].items()
                    if k in RankingService._RATIONALE_ALLOWLIST
                }
        return items
