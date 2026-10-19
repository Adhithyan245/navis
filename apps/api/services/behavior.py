import logging
from typing import Dict, Any, Optional, List, Set
from collections import defaultdict
from apps.api.services.behavior_storage import IBehaviorStorage, SQLAlchemyBehaviorStorage
from apps.api.services.behavior_queue import behavior_queue

logger = logging.getLogger(__name__)

class BehaviorTracker:
    def __init__(self, storage: Optional[IBehaviorStorage] = None):
        self._storage = storage or SQLAlchemyBehaviorStorage()

    # ─── RECORD INTERACTIONS (Non-blocking via BehaviorEventQueue) ───

    def record_query(self, user_id: int, domain: str, city: str, query: str):
        behavior_queue.enqueue_interaction(
            user_id=user_id, action_type="query", domain=domain, city=city, query=query
        )

    def record_click(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
        behavior_queue.enqueue_interaction(
            user_id=user_id, action_type="click", item_id=item_id, item_type=item_type,
            domain=domain, item_categories=categories
        )

    def record_save(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
        behavior_queue.enqueue_interaction(
            user_id=user_id, action_type="save", item_id=item_id, item_type=item_type,
            domain=domain, item_categories=categories
        )

    def record_ignore(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
        behavior_queue.enqueue_interaction(
            user_id=user_id, action_type="ignore", item_id=item_id, item_type=item_type,
            domain=domain, item_categories=categories
        )

    def record_dismiss(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
        behavior_queue.enqueue_interaction(
            user_id=user_id, action_type="dismiss", item_id=item_id, item_type=item_type,
            domain=domain, item_categories=categories
        )

    # ─── COMPUTE AFFINITIES (DB READS - Robust Exception Isolation) ───

    async def compute_adaptive_weights(self, user_id: int) -> Dict[str, float]:
        """
        Compute per-category weight adjustments from real behavior.
        Normalizes to 0.0-5.0 boost factor.
        """
        try:
            affinities = await self._storage.get_category_affinities(user_id)
            if not affinities:
                return {}

            max_count = max(affinities.values())
            if max_count == 0:
                return {}

            weights: Dict[str, float] = {}
            for cat, count in affinities.items():
                weights[cat] = round((count / max_count) * 5.0, 2)
            return weights
        except Exception as e:
            logger.warning(f"Database error in compute_adaptive_weights for user {user_id}: {e}")
            return {}  # Safe fallback

    async def compute_save_boost(self, user_id: int) -> float:
        """
        Compute save boost factor (0.0-1.5) based on user's save frequency.
        """
        try:
            save_count = await self._storage.get_save_count(user_id)
            if save_count >= 20:
                return 1.5
            elif save_count >= 6:
                return 1.0
            elif save_count >= 1:
                return 0.5
            return 0.0
        except Exception as e:
            logger.warning(f"Database error in compute_save_boost for user {user_id}: {e}")
            return 0.0  # Safe fallback

    async def get_ignored_categories(self, user_id: int, threshold: int = 5) -> List[str]:
        """
        Detect categories that the user actively avoids (frequent views/clicks, no saves).
        Supports click, dismiss, or ignore as avoidance signals.
        """
        try:
            view_and_click_cats = await self._storage.get_view_and_click_categories(user_id)
            saved_cats = await self._storage.get_saved_categories_set(user_id)

            ignored = []
            for cat, count in view_and_click_cats.items():
                if count >= threshold and cat not in saved_cats:
                    ignored.append(cat)
            return ignored
        except Exception as e:
            logger.warning(f"Database error in get_ignored_categories for user {user_id}: {e}")
            return []  # Safe fallback

    async def get_saved_refs(self, user_id: int, item_type: str = "") -> Set[str]:
        try:
            return await self._storage.get_saved_item_refs(user_id, item_type)
        except Exception as e:
            logger.warning(f"Database error in get_saved_refs for user {user_id}: {e}")
            return set()  # Safe fallback

    async def get_saved_items(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            return await self._storage.get_saved_items(user_id)
        except Exception as e:
            logger.warning(f"Database error in get_saved_items for user {user_id}: {e}")
            return []  # Safe fallback

    async def get_user_events_by_city(self, city: str) -> List[Dict[str, Any]]:
        try:
            return await self._storage.get_user_events_by_city(city)
        except Exception as e:
            logger.warning(f"Database error in get_user_events_by_city for city {city}: {e}")
            return []  # Safe fallback


class ContextMemoryService:
    def __init__(self, storage: Optional[IBehaviorStorage] = None):
        self._storage = storage or SQLAlchemyBehaviorStorage()

    def update_memory(
        self, user_id: int,
        search_entry: dict = None,
        domain: str = None,
        location: dict = None
    ):
        """Enqueue memory update to prevent HTTP stream blocking."""
        behavior_queue.enqueue_memory_update(
            user_id=user_id,
            search_entry=search_entry,
            domain=domain,
            location=location
        )

    async def get_memory(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            return await self._storage.get_context_memory(user_id)
        except Exception as e:
            logger.warning(f"Database error in get_memory for user {user_id}: {e}")
            return None  # Safe fallback

    async def get_top_categories(self, user_id: int, limit: int = 5) -> List[str]:
        try:
            affinities = await self._storage.get_category_affinities(user_id)
            if not affinities:
                return []
            sorted_cats = sorted(affinities.items(), key=lambda x: x[1], reverse=True)
            return [cat for cat, _ in sorted_cats[:limit]]
        except Exception as e:
            logger.warning(f"Database error in get_top_categories for user {user_id}: {e}")
            return []  # Safe fallback

    async def get_recent_queries(self, user_id: int, limit: int = 5) -> List[str]:
        try:
            mem = await self.get_memory(user_id)
            if not mem:
                return []
            searches = mem.get("recent_searches", [])
            return [s.get("query", "") for s in searches[-limit:] if s.get("query")]
        except Exception as e:
            logger.warning(f"Database error in get_recent_queries for user {user_id}: {e}")
            return []  # Safe fallback


# Expose global singletons
behavior_tracker = BehaviorTracker()
context_memory = ContextMemoryService()
