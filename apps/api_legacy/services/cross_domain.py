"""
Cross-domain scoring and aggregation.

Handles queries that span multiple domains:
  - "coworking near tonight's event"
  - "pharmacy near start of route"
  - "restaurants matching saved places"

Combines results by:
  - Distance between anchor points
  - User preferences for both domains
  - Time relevance (events + schedules)
  - Category affinity weights

All signals are DB-backed or provider-sourced. Never fabricates.
"""

import math
from typing import List, Dict, Any, Optional, Set, Tuple
from models.context import UserContext
from services.time_context import TimeContext


class CrossDomainScorer:
    """Score and rank results from multiple domains together."""

    def _calculate_distance(self, lat1, lon1, lat2, lon2) -> float:
        """Haversine distance in km."""
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

    def score_place_event_pair(
        self,
        place: Dict[str, Any],
        event: Dict[str, Any],
        context: UserContext,
        user_prefs_match: float = 0.0,
        time_ctx: Optional[TimeContext] = None,
    ) -> float:
        """
        Score a place-event pair for "coworking near tonight's event" queries.
        Takes into account:
          - Distance from event to place
          - Place quality (rating)
          - Event relevance to user
          - Time relevance (event date matters)

        Returns combined score.
        """
        score = 0.0
        tc = time_ctx or TimeContext()

        # 1. Distance from event to working space
        place_loc = place.get("location", {})
        event_loc = event.get("location", {})

        if place_loc.get("lat") and event_loc.get("lat"):
            dist = self._calculate_distance(
                event_loc["lat"], event_loc.get("lng", 0),
                place_loc["lat"], place_loc.get("lng", 0),
            )
            # Prefer places within 2km of event
            if dist <= 0.5:
                score += 8.0
            elif dist <= 1.0:
                score += 6.0
            elif dist <= 2.0:
                score += 4.0
            else:
                score -= (dist - 2.0) * 0.5  # Penalty beyond 2km

        # 2. Place rating boost
        rating = float(place.get("rating", 0))
        score += rating * 1.0

        # 3. Event time relevance
        is_relevant = tc.is_relevant_time(event)
        if is_relevant:
            score += 3.0

        # 4. User preference overlap
        score += user_prefs_match * 2.0

        return max(0.0, score)  # Floor at 0

    def score_place_place_pair(
        self,
        anchor_place: Dict[str, Any],
        nearby_place: Dict[str, Any],
        context: UserContext,
        max_distance_km: float = 5.0,
    ) -> float:
        """
        Score a pair of places for "restaurants near saved location" queries.
        Takes into account:
          - Distance from anchor
          - Both places matching user preferences
          - Combined rating

        Returns score or None if too far away.
        """
        score = 0.0

        anchor_loc = anchor_place.get("location", {})
        nearby_loc = nearby_place.get("location", {})

        if anchor_loc.get("lat") and nearby_loc.get("lat"):
            dist = self._calculate_distance(
                anchor_loc["lat"], anchor_loc.get("lng", 0),
                nearby_loc["lat"], nearby_loc.get("lng", 0),
            )

            # Enforce max distance
            if dist > max_distance_km:
                return 0.0

            # Distance score: closer is better
            demerits = dist * 0.5
            score -= demerits

        # Nearby place quality
        rating = float(nearby_place.get("rating", 0))
        score += rating * 1.5

        # Type matching to user preferences
        nearby_types = [t.lower() for t in nearby_place.get("types", [])]
        for pref in context.preferences:
            if pref.lower() in nearby_types:
                score += 3.0

        return max(0.0, score)

    def aggregate_place_event_results(
        self,
        places: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        context: UserContext,
        behavior_weights: Optional[Dict[str, float]] = None,
        time_ctx: Optional[TimeContext] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate place and event results into combined recommendations.
        Returns list of combined results sorted by cross-domain score.
        """
        behavior_weights = behavior_weights or {}
        tc = time_ctx or TimeContext()
        combined = []

        # Score all place-event pairs
        for place in places:
            for event in events:
                # Compute preference match
                event_title = event.get("title", "").lower()
                place_types = [t.lower() for t in place.get("types", [])]

                pref_match = 0.0
                for pref in context.preferences:
                    pref_lower = pref.lower()
                    if pref_lower in event_title or pref_lower in place_types:
                        pref_match += 1.0

                score = self.score_place_event_pair(
                    place, event, context,
                    user_prefs_match=pref_match,
                    time_ctx=tc,
                )

                if score > 0:
                    combined.append({
                        "type": "place_event_pair",
                        "place": place,
                        "event": event,
                        "score": round(score, 2),
                        "rationale": {
                            "pair_type": "coworking_near_event",
                            "distance_based": True,
                            "time_relevant": tc.is_relevant_time(event),
                            "preference_match": pref_match > 0,
                        },
                    })

        # Sort by score descending
        combined.sort(key=lambda x: x["score"], reverse=True)

        return combined[:limit]

    def aggregate_settings(
        self,
        anchor_place: Dict[str, Any],
        nearby_places: List[Dict[str, Any]],
        context: UserContext,
        max_distance_km: float = 5.0,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recommend places near a saved/anchor location.
        Example: "Restaurants near my favorite coffee shop"
        """
        scored = []

        for place in nearby_places:
            score = self.score_place_place_pair(
                anchor_place, place, context, max_distance_km
            )

            if score > 0:
                anchor_loc = anchor_place.get("location", {})
                place_loc = place.get("location", {})
                dist = self._calculate_distance(
                    anchor_loc["lat"], anchor_loc.get("lng", 0),
                    place_loc["lat"], place_loc.get("lng", 0),
                ) if anchor_loc.get("lat") and place_loc.get("lat") else None

                scored.append({
                    "type": "nearby_place",
                    "anchor": anchor_place.get("name", ""),
                    "place": place,
                    "distance_km": round(dist, 2) if dist else None,
                    "score": round(score, 2),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]


# Singleton instance
cross_domain_scorer = CrossDomainScorer()
