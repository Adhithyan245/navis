import abc
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict
from sqlalchemy.future import select
from sqlalchemy import func, desc
from apps.api.database import AsyncSessionLocal
from apps.api.models.db_models import UserInteraction, ContextMemory, SavedItem, SourceAuditLog, UserEvent

class IBehaviorStorage(abc.ABC):
    @abc.abstractmethod
    async def save_interaction(
        self, user_id: int, action_type: str,
        item_id: Optional[str] = None, item_type: Optional[str] = None,
        domain: Optional[str] = None, city: Optional[str] = None,
        query: Optional[str] = None, item_categories: Optional[list] = None
    ) -> None:
        pass

    @abc.abstractmethod
    async def get_category_affinities(self, user_id: int, limit: int = 50) -> Dict[str, int]:
        pass

    @abc.abstractmethod
    async def get_domain_frequency(self, user_id: int, limit: int = 30) -> Dict[str, int]:
        pass

    @abc.abstractmethod
    async def get_saved_categories(self, user_id: int) -> Dict[str, int]:
        pass

    @abc.abstractmethod
    async def get_save_count(self, user_id: int) -> int:
        pass

    @abc.abstractmethod
    async def get_view_and_click_categories(self, user_id: int) -> Dict[str, int]:
        pass

    @abc.abstractmethod
    async def get_saved_categories_set(self, user_id: int) -> Set[str]:
        pass

    @abc.abstractmethod
    async def update_context_memory(
        self, user_id: int,
        search_entry: Optional[dict] = None,
        domain: Optional[str] = None,
        location: Optional[dict] = None,
        category_affinities: Optional[dict] = None,
        max_searches: int = 15,
        max_domains: int = 15,
        max_locations: int = 10
    ) -> None:
        pass

    @abc.abstractmethod
    async def get_context_memory(self, user_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    async def get_saved_item_refs(self, user_id: int, item_type: str = "") -> Set[str]:
        pass

    @abc.abstractmethod
    async def save_audit_log(
        self, user_id: Optional[int], endpoint: str,
        live_apis_used: dict, db_queries_used: list,
        fallback_triggers: list
    ) -> None:
        pass

    @abc.abstractmethod
    async def get_saved_items(self, user_id: int) -> List[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    async def get_user_events_by_city(self, city: str) -> List[Dict[str, Any]]:
        pass


class SQLAlchemyBehaviorStorage(IBehaviorStorage):
    """Concrete repository using SQLAlchemy async database connection."""

    async def save_interaction(
        self, user_id: int, action_type: str,
        item_id: Optional[str] = None, item_type: Optional[str] = None,
        domain: Optional[str] = None, city: Optional[str] = None,
        query: Optional[str] = None, item_categories: Optional[list] = None
    ) -> None:
        async with AsyncSessionLocal() as session:
            session.add(UserInteraction(
                user_id=user_id, item_id=item_id, item_type=item_type,
                action_type=action_type, domain=domain, city=city,
                query=query, item_categories=item_categories
            ))
            await session.commit()

    async def get_category_affinities(self, user_id: int, limit: int = 50) -> Dict[str, int]:
        affinities: Dict[str, int] = defaultdict(int)
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
        return dict(affinities)

    async def get_domain_frequency(self, user_id: int, limit: int = 30) -> Dict[str, int]:
        freq: Dict[str, int] = defaultdict(int)
        async with AsyncSessionLocal() as session:
            q = (
                select(UserInteraction.domain, func.count(UserInteraction.id))
                .where(UserInteraction.user_id == user_id)
                .where(UserInteraction.domain.isnot(None))
                .group_by(UserInteraction.domain)
                .limit(limit)
            )
            result = await session.execute(q)
            for domain, count in result.all():
                freq[domain] = count
        return dict(freq)

    async def get_saved_categories(self, user_id: int) -> Dict[str, int]:
        cats: Dict[str, int] = defaultdict(int)
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
        return dict(cats)

    async def get_save_count(self, user_id: int) -> int:
        async with AsyncSessionLocal() as session:
            q = (
                select(func.count(UserInteraction.id))
                .where(UserInteraction.user_id == user_id)
                .where(UserInteraction.action_type == "save")
            )
            result = await session.execute(q)
            return result.scalar() or 0

    async def get_view_and_click_categories(self, user_id: int) -> Dict[str, int]:
        views: Dict[str, int] = defaultdict(int)
        async with AsyncSessionLocal() as session:
            q = (
                select(UserInteraction.item_categories)
                .where(UserInteraction.user_id == user_id)
                .where(UserInteraction.action_type.in_(["view", "click"]))
                .where(UserInteraction.item_categories.isnot(None))
            )
            result = await session.execute(q)
            for row in result.scalars():
                if isinstance(row, list):
                    for cat in row:
                        if isinstance(cat, str):
                            views[cat.lower()] += 1
        return dict(views)

    async def get_saved_categories_set(self, user_id: int) -> Set[str]:
        saved_cats = set()
        async with AsyncSessionLocal() as session:
            q_saved = (
                select(UserInteraction.item_categories)
                .where(UserInteraction.user_id == user_id)
                .where(UserInteraction.action_type == "save")
                .where(UserInteraction.item_categories.isnot(None))
            )
            result_saved = await session.execute(q_saved)
            for row in result_saved.scalars():
                if isinstance(row, list):
                    for cat in row:
                        if isinstance(cat, str):
                            saved_cats.add(cat.lower())
        return saved_cats

    async def update_context_memory(
        self, user_id: int,
        search_entry: Optional[dict] = None,
        domain: Optional[str] = None,
        location: Optional[dict] = None,
        category_affinities: Optional[dict] = None,
        max_searches: int = 15,
        max_domains: int = 15,
        max_locations: int = 10
    ) -> None:
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
                searches = list(mem.recent_searches or [])
                searches.append(search_entry)
                # Apply strict bounded context memory retention policy
                mem.recent_searches = searches[-max_searches:]

            if domain:
                domains = list(mem.recent_domains or [])
                domains.append(domain)
                mem.recent_domains = domains[-max_domains:]

            if location and location.get("lat"):
                locs = list(mem.recent_locations or [])
                locs.append(location)
                mem.recent_locations = locs[-max_locations:]

            if category_affinities:
                mem.category_affinities = category_affinities

            await session.commit()

    async def get_context_memory(self, user_id: int) -> Optional[Dict[str, Any]]:
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
        return None

    async def get_saved_item_refs(self, user_id: int, item_type: str = "") -> Set[str]:
        async with AsyncSessionLocal() as session:
            q = select(SavedItem.item_ref).where(SavedItem.user_id == user_id)
            if item_type:
                q = q.where(SavedItem.item_type == item_type)
            result = await session.execute(q)
            return {r[0] for r in result.all() if r[0]}

    async def save_audit_log(
        self, user_id: Optional[int], endpoint: str,
        live_apis_used: dict, db_queries_used: list,
        fallback_triggers: list
    ) -> None:
        async with AsyncSessionLocal() as session:
            session.add(SourceAuditLog(
                user_id=user_id, endpoint=endpoint,
                live_apis_used=live_apis_used,
                db_queries_used=db_queries_used,
                fallback_triggers=fallback_triggers
            ))
            await session.commit()

    async def get_user_events_by_city(self, city: str) -> List[Dict[str, Any]]:
        events = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserEvent).where(UserEvent.city == city))
            for row in result.scalars():
                if row and row.id and row.title:
                    events.append({
                        "id": str(row.id), "title": row.title,
                        "start_time": str(row.date) if row.date else "",
                        "location": {"name": None, "lat": row.lat, "lng": row.lng},
                        "source_type": "user_created", "source": "user_events_db"
                    })
        return events

    async def get_saved_items(self, user_id: int) -> List[Dict[str, Any]]:
        items = []
        async with AsyncSessionLocal() as session:
            q = select(SavedItem).where(SavedItem.user_id == user_id)
            result = await session.execute(q)
            for row in result.scalars():
                items.append({
                    "id": str(row.id),
                    "type": row.item_type,
                    "ref": row.item_ref,
                    "snapshot": row.snapshot,
                    "created_at": str(row.created_at)
                })
        return items
