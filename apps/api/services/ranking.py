import math
from typing import List, Dict, Any, Optional, Set
from apps.api.models.context import UserContext

BUDGET_TO_PRICE_RANGE: Dict[str, tuple] = {
    "low": (0, 1),
    "medium": (1, 2),
    "high": (2, 4),
}

class RankingService:
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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

        if anchor_location is None:
            if context.home_anchor and context.home_anchor.get("lat"):
                anchor_location = context.home_anchor
            elif context.work_anchor and context.work_anchor.get("lat"):
                anchor_location = context.work_anchor

        scored = []
        for idx, p in enumerate(places):
            # Detailed score breakdown for transparency
            base_score = 0.0
            preference_score = 0.0
            distance_penalty = 0.0
            dislike_penalty = 0.0
            saved_boost = 0.0

            # 1. Rating (float 0-5)
            rating = float(p.get("rating", 0))
            base_score += rating * 2

            # 2. Distance from anchor (Haversine)
            loc = p.get("location", {})
            distance_km = None
            if anchor_location and loc.get("lat") and anchor_location.get("lat"):
                distance_km = self._calculate_distance(
                    float(anchor_location["lat"]), float(anchor_location.get("lng", 0)),
                    float(loc["lat"]), float(loc.get("lng", 0))
                )
                distance_penalty = distance_km * 0.5

            # 3. Preference match
            types_lower = [t.lower() for t in p.get("types", [])]
            for pref in (context.preferences or []):
                if pref.lower() in types_lower:
                    preference_score += 5.0

            # 4. Food preference match
            for fp in (context.food_preferences or []):
                if fp.lower() in types_lower:
                    preference_score += 3.0

            # 5. Dislike penalty
            for dislike in (context.dislikes or []):
                if dislike.lower() in types_lower:
                    dislike_penalty += 10.0

            # 6. Price level
            price_level = p.get("price_level")
            if price_level is not None and context.budget:
                budget_range = BUDGET_TO_PRICE_RANGE.get(context.budget)
                if budget_range:
                    if budget_range[0] <= price_level <= budget_range[1]:
                        base_score += 3.0
                    elif price_level > budget_range[1]:
                        base_score -= 2.0

            # 7. Open now
            if p.get("open_now") is True:
                base_score += 2.0

            # 8. Saved boost
            place_id = p.get("place_id", "")
            is_saved = place_id in saved_item_refs
            if is_saved:
                base_saved_boost = 4.0
                saved_boost = base_saved_boost * (1.0 + save_boost)

            # ─── ADAPTIVE BEHAVIOR SIGNALS (ADDITIVE ONLY) ───
            # 9. Behavior-based category boost
            behavior_boost = 0.0
            for cat_type in types_lower:
                if cat_type in behavior_weights:
                    behavior_boost += behavior_weights[cat_type]

            # 10. Ignored category penalty
            ignored_penalty = 0.0
            for cat_type in types_lower:
                if cat_type in ignored_categories:
                    ignored_penalty += 0.5

            # Compute final aggregate score
            score = (
                base_score +
                preference_score -
                distance_penalty -
                dislike_penalty +
                saved_boost +
                behavior_boost -
                ignored_penalty
            )

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

            # Inject detailed explainable breakdown
            rationale["score_breakdown"] = {
                "base_score": round(base_score, 2),
                "preference_score": round(preference_score, 2),
                "distance_penalty": round(distance_penalty, 2),
                "dislike_penalty": round(dislike_penalty, 2),
                "saved_boost": round(saved_boost, 2),
                "behavior_boost": round(behavior_boost, 2),
                "ignored_penalty": round(ignored_penalty, 2),
                "final_score": round(score, 2)
            }

            p["_rank"] = {"score": round(score, 2), "idx": idx}
            p["rationale"] = rationale
            scored.append(p)

        # Stable tie-breaking: original order preserved
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

            preference_score = 0.0
            saved_boost = 0.0
            behavior_boost = 0.0
            ignored_penalty = 0.0

            # 1. Preference match in title
            for pref in (context.preferences or []):
                if pref.lower() in title:
                    preference_score += 5.0

            # 2. Event category match
            for cat in (context.event_categories or []):
                if cat.lower() in title:
                    preference_score += 4.0

            # 3. Saved boost
            event_id = e.get("id", "")
            if event_id in saved_item_refs:
                saved_boost += 3.0

            # 4. Behavior boost for event categories
            categories = e.get("categories", [])
            if isinstance(categories, list):
                for cat in categories:
                    if isinstance(cat, str):
                        cat_lower = cat.lower()
                        if cat_lower in behavior_weights:
                            behavior_boost += behavior_weights[cat_lower]
                        if cat_lower in ignored_categories:
                            ignored_penalty += 0.5

            score = preference_score + saved_boost + behavior_boost - ignored_penalty

            rationale = {
                "score_breakdown": {
                    "preference_score": round(preference_score, 2),
                    "saved_boost": round(saved_boost, 2),
                    "behavior_boost": round(behavior_boost, 2),
                    "ignored_penalty": round(ignored_penalty, 2),
                    "final_score": round(score, 2)
                }
            }

            e["_rank"] = {"score": round(score, 2), "idx": idx}
            e["rationale"] = rationale
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
            distance_penalty = 0.0
            behavior_boost = 0.0
            ignored_penalty = 0.0

            if anchor_location and loc.get("lat") and anchor_location.get("lat"):
                distance_km = self._calculate_distance(
                    float(anchor_location["lat"]), float(anchor_location.get("lng", 0)),
                    float(loc["lat"]), float(loc.get("lng", 0))
                )
                distance_penalty = distance_km * 0.3

            # Behavior boost for service types
            service_type = s.get("type", "").lower()
            if service_type in behavior_weights:
                behavior_boost += behavior_weights[service_type]
            if service_type in ignored_categories:
                ignored_penalty += 0.5

            score = behavior_boost - distance_penalty - ignored_penalty

            rationale = {}
            if distance_km is not None:
                rationale["distance_km"] = round(distance_km, 2)

            rationale["score_breakdown"] = {
                "distance_penalty": round(distance_penalty, 2),
                "behavior_boost": round(behavior_boost, 2),
                "ignored_penalty": round(ignored_penalty, 2),
                "final_score": round(score, 2)
            }

            s["_rank"] = {"score": round(score, 2), "idx": idx}
            s["rationale"] = rationale
            scored.append(s)

        scored.sort(key=lambda x: (x["_rank"]["score"], -x["_rank"]["idx"]), reverse=True)
        return scored

    # Rationale keys permitted in API responses — strictly enforced
    _RATIONALE_ALLOWLIST = frozenset({
        "rating", "distance_km", "price_level",
        "open_now", "saved", "behavior_affinity_boost",
        "score_breakdown"
    })

    @staticmethod
    def strip_ranking_metadata(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove internal _rank keys and enforce rationale boundary before sending to client."""
        for item in items:
            item.pop("_rank", None)
            item.pop("_ranking_score", None)
            if "rationale" in item and isinstance(item["rationale"], dict):
                item["rationale"] = {
                    k: v for k, v in item["rationale"].items()
                    if k in RankingService._RATIONALE_ALLOWLIST
                }
        return items

ranking_service = RankingService()
