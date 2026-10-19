"""
User behavior tracking and adaptive weight computation.

Tracks: clicks, saves, views, rsvps, queries.
Computes: category affinities, domain frequency, adaptive weight adjustments.

All signals are DB-backed — never fabricated.
"""

import time
from typing import Dict, Any, Optional, List
from collections import defaultdict
from database import AsyncSessionLocal
from models.db_models import UserInteraction, ContextMemory
from sqlalchemy.future import select
from sqlalchemy import func, desc


class BehaviorTracker:

    # ─── RECORD INTERACTIONS ───

    async def record(
        self, user_id: int, action_type: str,
        item_id: str = None, item_type: str = None,
        domain: str = None, city: str = None,
        query: str = None, item_categories: list = None,
    ):
        """Record a single user interaction."""
        try:
            async with AsyncSessionLocal() as session:
                session.add(UserInteraction(
                    user_id=user_id, item_id=item_id, item_type=item_type,
                    action_type=action_type, domain=domain, city=city,
                    query=query, item_categories=item_categories,
                ))
                await session.commit()
        except Exception:
            pass

    async def record_query(self, user_id: int, domain: str, city: str, query: str):
        await self.record(user_id, "query", domain=domain, city=city, query=query)

    async def record_click(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
        await self.record(user_id, "click", item_id=item_id, item_type=item_type, domain=domain, item_categories=categories)

    async def record_save(self, user_id: int, item_id: str, item_type: str, domain: str, categories: list = None):
        await self.record(user_id, "save", item_id=item_id, item_type=item_type, domain=domain, item_categories=categories)

    # ─── COMPUTE AFFINITIES ───

    async def get_category_affinities(self, user_id: int, limit: int = 50) -> Dict[str, int]:
        """Count category occurrences across clicks and saves. Returns {category: count}."""
        affinities: Dict[str, int] = defaultdict(int)
        try:
            async with AsyncSessionLocal() as session:
                q = (
                    select(UserInteraction.item_categories)
                    .where(UserInteraction.user_id == user_id)
                    .where(UserInteraction.action_type.in_(["click", "save"]))
                    .where(UserInteraction.item_categories.isnot(None))
                    .order_by(desc(UserInteraction.created_at))
                    .limit(limit)
                )
                result = await session.execute(q)
                for row in result.scalars():
                    if isinstance(row, list):
                        for cat in row:
                            if isinstance(cat, str):
                                affinities[cat.lower()] += 1
        except Exception:
            pass
        return dict(affinities)

    async def get_domain_frequency(self, user_id: int, limit: int = 30) -> Dict[str, int]:
        """Count how often user visits each domain. Returns {domain: count}."""
        freq: Dict[str, int] = defaultdict(int)
        try:
            async with AsyncSessionLocal() as session:
                q = (
                    select(UserInteraction.domain, func.count(UserInteraction.id))
                    .where(UserInteraction.user_id == user_id)
                    .where(UserInteraction.domain.isnot(None))
                    .group_by(UserInteraction.domain)
                )
                result = await session.execute(q)
                for domain, count in result.all():
                    freq[domain] = count
        except Exception:
            pass
        return dict(freq)

    async def get_saved_categories(self, user_id: int) -> Dict[str, int]:
        """Count categories from saved items specifically."""
        cats: Dict[str, int] = defaultdict(int)
        try:
            async with AsyncSessionLocal() as session:
                q = (
                    select(UserInteraction.item_categories)
                    .where(UserInteraction.user_id == user_id)
                    .where(UserInteraction.action_type == "save")
                    .where(UserInteraction.item_categories.isnot(None))
                )
                result = await session.execute(q)
                for row in result.scalars():
                    if isinstance(row, list):
                        for cat in row:
                            if isinstance(cat, str):
                                cats[cat.lower()] += 1
        except Exception:
            pass
        return dict(cats)

    async def compute_adaptive_weights(self, user_id: int) -> Dict[str, float]:
        """
        Compute per-category weight adjustments from real behavior.
        Returns {category: weight_boost} where boost is 0.0-5.0.
        Categories the user clicks/saves get boosted.
        Categories the user never interacts with get no boost (0.0).
        """
        affinities = await self.get_category_affinities(user_id)
        if not affinities:
            return {}

        max_count = max(affinities.values())
        if max_count == 0:
            return {}

        weights: Dict[str, float] = {}
        for cat, count in affinities.items():
            # Normalize to 0-5 range based on relative interaction frequency
            weights[cat] = round((count / max_count) * 5.0, 2)
        return weights

    async def compute_save_boost(self, user_id: int) -> float:
        """
        Compute save boost factor (0.0-2.0).
        Users who save frequently get tighter save boost.
        Users who never save get 0.0.
        """
        try:
            async with AsyncSessionLocal() as session:
                q = (
                    select(func.count(UserInteraction.id))
                    .where(UserInteraction.user_id == user_id)
                    .where(UserInteraction.action_type == "save")
                )
                result = await session.execute(q)
                save_count = result.scalar() or 0
                # Logarithmic scale: 1-5 saves → 0.5, 6-20 saves → 1.0, 20+ → 1.5
                if save_count >= 20:
                    return 1.5
                elif save_count >= 6:
                    return 1.0
                elif save_count >= 1:
                    return 0.5
        except Exception:
            pass
        return 0.0

    async def get_ignored_categories(self, user_id: int, threshold: int = 5) -> List[str]:
        """
        Detect categories that user actively avoids (frequent views, no saves).
        Returns list of categories to slightly downrank.
        """
        try:
            async with AsyncSessionLocal() as session:
                q = (
                    select(UserInteraction.item_categories)
                    .where(UserInteraction.user_id == user_id)
                    .where(UserInteraction.action_type.in_(["view", "click"]))
                    .where(UserInteraction.item_categories.isnot(None))
                )
                result = await session.execute(q)
                all_views = defaultdict(int)
                for row in result.scalars():
                    if isinstance(row, list):
                        for cat in row:
                            if isinstance(cat, str):
                                all_views[cat.lower()] += 1

                # Categories viewed 5+ times but never saved = ignored
                q_saved = (
                    select(UserInteraction.item_categories)
                    .where(UserInteraction.user_id == user_id)
                    .where(UserInteraction.action_type == "save")
                    .where(UserInteraction.item_categories.isnot(None))
                )
                result_saved = await session.execute(q_saved)
                saved_cats = set()
                for row in result_saved.scalars():
                    if isinstance(row, list):
                        for cat in row:
                            if isinstance(cat, str):
                                saved_cats.add(cat.lower())

                ignored = []
                for cat, count in all_views.items():
                    if count >= threshold and cat not in saved_cats:
                        ignored.append(cat)
                return ignored
        except Exception:
            pass
        return []


# ─── CONTEXT MEMORY ───

class ContextMemoryService:
    """Persists and retrieves recent user context for adaptive suggestions."""

    async def update_memory(
        self, user_id: int,
        search_entry: dict = None,
        domain: str = None,
        location: dict = None,
        category_affinities: dict = None,
    ):
        try:
            async with AsyncSessionLocal() as session:
                q = select(ContextMemory).where(ContextMemory.user_id == user_id)
                result = await session.execute(q)
                mem = result.scalar_one_or_none()

                if mem is None:
                    mem = ContextMemory(
                        user_id=user_id,
                        recent_searches=[], recent_domains=[],
                        recent_locations=[], category_affinities={},
                    )
                    session.add(mem)

                if search_entry:
                    searches = (mem.recent_searches or [])[-49:]  # keep last 50
                    searches.append(search_entry)
                    mem.recent_searches = searches

                if domain:
                    domains = (mem.recent_domains or [])[-49:]  # keep last 50
                    domains.append(domain)
                    mem.recent_domains = domains

                if location and location.get("lat"):
                    locs = (mem.recent_locations or [])[-49:]  # keep last 50
                    locs.append(location)
                    mem.recent_locations = locs

                if category_affinities:
                    mem.category_affinities = category_affinities

                await session.commit()
        except Exception:
            pass

    async def get_memory(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            async with AsyncSessionLocal() as session:
                q = select(ContextMemory).where(ContextMemory.user_id == user_id)
                result = await session.execute(q)
                mem = result.scalar_one_or_none()
                if mem:
                    return {
                        "recent_searches": mem.recent_searches or [],
                        "recent_domains": mem.recent_domains or [],
                        "recent_locations": mem.recent_locations or [],
                        "category_affinities": mem.category_affinities or {},
                    }
        except Exception:
            pass
        return None

    async def get_top_categories(self, user_id: int, limit: int = 5) -> List[str]:
        """Get user's top-clicked/saved categories."""
        affinities = await BehaviorTracker().get_category_affinities(user_id)
        if not affinities:
            return []
        sorted_cats = sorted(affinities.items(), key=lambda x: x[1], reverse=True)
        return [cat for cat, _ in sorted_cats[:limit]]

    async def get_recent_queries(self, user_id: int, limit: int = 5) -> List[str]:
        mem = await self.get_memory(user_id)
        if not mem:
            return []
        searches = mem.get("recent_searches", [])
        return [s.get("query", "") for s in searches[-limit:] if s.get("query")]


behavior_tracker = BehaviorTracker()
context_memory = ContextMemoryService()
