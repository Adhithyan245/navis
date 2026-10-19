"""
Smart suggestions engine.

Generates context-aware suggestions from:
  - user behavior (category affinities from DB)
  - city capabilities (from registry)
  - time context (from system clock)
  - recent searches (from context memory)

NEVER fabricates data. Suggestions are actionable navigation hints only.
"""

from typing import List, Dict, Any, Optional
from services.time_context import TimeContext
from services.behavior import BehaviorTracker, ContextMemoryService


class SuggestionsEngine:
    def __init__(self):
        self.behavior_tracker = BehaviorTracker()
        self.context_memory = ContextMemoryService()

    async def for_empty_state(
        self,
        domain: str,
        city_capabilities: Dict[str, bool],
        user_id: Optional[int] = None,
        category_affinities: Dict[str, float] = None,
        recent_domains: List[str] = None,
        time_ctx: TimeContext = None,
    ) -> List[str]:
        """Generate suggestions when a domain returns empty."""
        suggestions = []
        tc = time_ctx or TimeContext()

        # Fetch real affinities if user_id provided
        if user_id and not category_affinities:
            category_affinities = await self.behavior_tracker.get_category_affinities(user_id)
        affinities = category_affinities or {}

        # Fetch recent domains if not provided
        if user_id and not recent_domains:
            mem = await self.context_memory.get_memory(user_id)
            recent_domains = mem.get("recent_domains", []) if mem else []
        recent = recent_domains or []

        if domain == "explore":
            if affinities:
                top = sorted(affinities.items(), key=lambda x: x[1], reverse=True)[:2]
                suggestions.extend([f"Try more: {cat.replace('_', ' ')}" for cat, _ in top])
            if city_capabilities.get("events"):
                suggestions.append("Check Connect for events nearby")
            suggestions.append("Try a different neighborhood")

        elif domain == "connect":
            suggestions.append("Create a community event")
            if city_capabilities.get("places"):
                suggestions.append("Explore places instead")
            if tc.time_of_day == "evening":
                suggestions.append("Try: what's happening tonight")
            else:
                suggestions.append("Check back later for new events")

        elif domain == "services":
            suggestions.append("Try a different service category")
            if city_capabilities.get("places"):
                suggestions.append("Search Explore for nearby facilities")
            suggestions.append("Check local municipal websites")

        elif domain == "work":
            if affinities.get("cafe") or affinities.get("coffee"):
                suggestions.append("Search for cafes with wifi")
            suggestions.append("Try exploring a different area")
            if "explore" not in recent[-3:] if recent else []:
                suggestions.append("Try Explore for more options")

        elif domain == "move":
            suggestions.append("Use Explore to find walkable areas")
            if city_capabilities.get("places"):
                suggestions.append("Search for places near saved locations")

        elif domain == "settle":
            active = [k for k, v in city_capabilities.items() if v]
            if "places" in active:
                suggestions.append("Start with Explore to find your neighborhood")
            if "services" in active:
                suggestions.append("Check Services for nearby hospitals")
            if "events" in active:
                suggestions.append("Use Connect to find community events")

        else:
            suggestions.append("Try Explore for places")
            suggestions.append("Try Connect for events")

        return suggestions[:4]

    async def for_home(
        self,
        city_capabilities: Dict[str, bool],
        user_id: Optional[int] = None,
        category_affinities: Dict[str, float] = None,
        recent_domains: List[str] = None,
        time_ctx: TimeContext = None,
    ) -> List[str]:
        """Generate smart suggestions for the home dashboard."""
        suggestions = []
        tc = time_ctx or TimeContext()

        # Fetch real data if user_id provided
        if user_id and not category_affinities:
            category_affinities = await self.behavior_tracker.get_category_affinities(user_id)
        affinities = category_affinities or {}

        if user_id and not recent_domains:
            mem = await self.context_memory.get_memory(user_id)
            recent_domains = mem.get("recent_domains", []) if mem else []
        recent = recent_domains or []

        # Time-aware
        if tc.time_of_day == "morning" and city_capabilities.get("places"):
            suggestions.append("☀️ Find a coffee shop nearby")
        if tc.time_of_day == "evening" and city_capabilities.get("events"):
            suggestions.append("🌙 See what's happening tonight")
        if tc.day_type == "weekend" and city_capabilities.get("events"):
            suggestions.append("🎉 Explore weekend activities")

        # Behavior-aware: top category
        if affinities:
            top_items = sorted(affinities.items(), key=lambda x: x[1], reverse=True)[:1]
            for cat, _ in top_items:
                suggestions.append(f"More {cat.replace('_', ' ')} places")

        # Under-used domains
        active_domains = {k for k, v in city_capabilities.items() if v}
        used = set(recent[-10:]) if recent else set()
        unused = active_domains - used - {"work", "home"}
        for d in list(unused)[:1]:
            suggestions.append(f"Try {d.capitalize()}")

        return suggestions[:4]

    async def for_partial_results(
        self,
        domain: str,
        result_count: int,
        city_capabilities: Dict[str, bool],
        user_id: Optional[int] = None,
        time_ctx: TimeContext = None,
    ) -> List[str]:
        """Generate suggestions when domain returns partial results."""
        suggestions = []
        tc = time_ctx or TimeContext()

        if domain == "explore":
            suggestions.append("Narrow your neighborhood")
            if city_capabilities.get("services"):
                suggestions.append("Try Services for specific needs")
            if city_capabilities.get("events"):
                suggestions.append("Check Connect for nearby events")

        elif domain == "connect":
            if tc.time_of_day == "evening":
                suggestions.append("Try: events this week")
            if city_capabilities.get("places"):
                suggestions.append("Match venues with Explore")

        elif domain == "work":
            if city_capabilities.get("explore"):
                suggestions.append("Use Explore to see all options")

        else:
            suggestions.append("Try a different search")

        return suggestions[:3]
