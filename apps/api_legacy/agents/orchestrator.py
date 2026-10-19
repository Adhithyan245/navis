import asyncio
import logging
from typing import AsyncGenerator, Set
from models.context import UserContext
from models.response import APIResponse
from models.stream import StreamEvent
from utils.safety import safe_user_id as _safe_user_id, safe_emit_event
from services.provider_manager import ProviderManager
from services.ranking import RankingService
from services.metrics import metrics
from services.behavior import BehaviorTracker, ContextMemoryService
from services.time_context import TimeContext
from services.response_validator import ResponseValidator, response_validator
from agents.planner import AgentPlanner
from services.fusion import FusionEngine
from services.verification import VerificationService
from services.neighborhoods import NeighborhoodIntelligenceService
from services.memory.faiss_provider import FAISSMemoryProvider
from services.local_llm import HumanizationService
from core.observability import (
    new_trace, get_trace, build_debug_block, classify_service_reason
)
from database import AsyncSessionLocal
from models.db_models import UserEvent, SavedItem, SourceAuditLog
from sqlalchemy.future import select

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    def __init__(self):
        self.provider_manager = ProviderManager()
        self.ranking_service = RankingService()
        self.behavior_tracker = BehaviorTracker()
        self.context_memory = ContextMemoryService()
        self.planner = AgentPlanner()
        self.fusion_engine = FusionEngine()
        self.verification_service = VerificationService()
        self.neighborhood_service = NeighborhoodIntelligenceService()
        self.memory_provider = FAISSMemoryProvider()
        self.humanization_service = HumanizationService()

    # ─── PHASE 2: RESPONSE BUILDERS (Schema-Safe) ───

    def build_success_response(
        self,
        data: dict = None,
        sources: list = None,
        source_mode: str = "live",
        explanation: str = "",
        agent: str = "unknown",
    ) -> APIResponse:
        """Build a schema-valid success response."""
        return response_validator.success(
            data=data or {},
            sources=sources or [],
            source_mode=source_mode,
            explanation=explanation,
            agent=agent,
        )

    def build_fallback_response(
        self,
        reason: str = "No data available",
        db_sources: list = None,
        suggestions: list = None,
        agent: str = "unknown",
        data: dict = None,
    ) -> APIResponse:
        """Build a schema-valid fallback response."""
        return response_validator.fallback(
            data=data or {},
            reason=reason,
            db_sources=db_sources or [],
            suggestions=suggestions,
            agent=agent,
        )

    def build_error_response(
        self,
        reason: str = "Internal error",
        agent: str = "unknown",
        suggestions: list = None,
    ) -> APIResponse:
        """Build a schema-valid error response."""
        return response_validator.error(
            reason=reason,
            agent=agent,
            suggestions=suggestions,
        )

    async def _yield_event(self, state: str, progress: int, data: dict = None) -> str:
        """Emit a safe NDJSON event — validates state, never crashes."""
        return safe_emit_event(state, progress, data)

    async def _log_audit(self, endpoint, providers_attempted, providers_succeeded, db_sources, fallback_reasons, user_id=None):
        try:
            async with AsyncSessionLocal() as session:
                session.add(SourceAuditLog(
                    user_id=user_id, endpoint=endpoint,
                    live_apis_used={"attempted": providers_attempted, "succeeded": providers_succeeded},
                    db_queries_used=db_sources, fallback_triggers=fallback_reasons,
                ))
                await session.commit()
        except Exception:
            pass

    def _determine_source_mode(self, live_sources: list, db_sources: list) -> str:
        has_live, has_db = bool(live_sources), bool(db_sources)
        if has_live and has_db: return "mixed"
        if has_live: return "live"
        if has_db: return "mixed"
        return "fallback"

    async def _get_saved_refs(self, user_id: str, item_type: str = "") -> Set[str]:
        refs: Set[str] = set()
        try:
            uid = _safe_user_id(user_id)
            async with AsyncSessionLocal() as session:
                q = select(SavedItem.item_ref).where(SavedItem.user_id == uid)
                if item_type:
                    q = q.where(SavedItem.item_type == item_type)
                result = await session.execute(q)
                refs = {r[0] for r in result.all() if r[0]}
        except Exception:
            pass
        return refs

    async def _traced_call(self, provider: str, action: str, coro):
        """Wrapper for external API calls to record traces and classify reasons."""
        import time
        from core.dependencies import APINotConfiguredError
        
        t0 = time.time()
        try:
            res = await coro
        except APINotConfiguredError as e:
            res = {
                "status": "error",
                "message": e.message,
                "_reason": "api_not_configured"
            }
        except Exception as e:
            res = {
                "status": "error",
                "message": str(e),
                "_reason": "http_error"
            }
            
        latency_ms = (time.time() - t0) * 1000
        
        success = res.get("status") == "success"
        reason = classify_service_reason(res)
        res["_reason"] = reason  # Inject for orchestrator logic
        
        if trace := get_trace():
            trace.record_call(
                provider=provider,
                action=action,
                success=success,
                latency_ms=latency_ms,
                reason=reason,
                detail=res.get("explanation") or res.get("message"),
            )
            if not success:
                trace.record_fallback(provider, reason or "unknown")
                
        return res

    async def _finalize_stream(self, final_response: APIResponse) -> str:
        """
        Validates response schema, applies humanization, and returns NDJSON event.
        PHASE 2: Enforces APIResponse schema consistency before serialization.
        """
        try:
            # PHASE 2: Apply response validation and consistency checks
            final_response = response_validator.apply_to_stream_response(
                final_response,
                domain=final_response.agent or "unknown",
                context=f"stream_{final_response.agent}",
                fail_on_error=False,  # Never crash; fallback to safe response
            )
        except Exception as e:
            logger.error(f"Response validation failed in _finalize_stream: {e}")
            # Return safe fallback if validation completely fails
            final_response = response_validator.fallback(
                reason="Response validation error",
                agent=final_response.agent,
            )

        try:
            from services.local_llm import HumanizationService
            hs = HumanizationService()
            ctx = final_response.context_used or {}
            # Fallback for status
            agent_name = final_response.agent if final_response.agent != "unknown" else "general"
            final_response.message = await hs.humanize(final_response.data, ctx, agent_name)
        except Exception as e:
            logger.error(f"Humanization failed: {e}")
            final_response.message = "Here is the information you requested."
            
        payload = final_response.model_dump()
        if debug := build_debug_block():
            payload["debug"] = debug
        return await self._yield_event("completed", 100, payload)

    async def _safe_record_query(self, user_id: int, domain: str, city: str, query: str):
        try:
            await self.behavior_tracker.record_query(user_id, domain, city, query)
        except Exception as e:
            logger.warning(f"Behavior tracking failed: {e}")

    async def _update_context_memory(self, user_id: int, query: str = None, domain: str = None, city: str = None, location: dict = None, categories: list = None):
        try:
            search_entry = None
            if query:
                search_entry = {"query": query, "domain": domain, "city": city}
                
            await self.context_memory.update_memory(
                user_id=user_id,
                search_entry=search_entry,
                domain=domain,
                location=location,
                category_affinities=None
            )
        except Exception as e:
            logger.warning(f"Context memory update failed: {e}")

    # ─── EXPLORE ───
    async def stream_explore(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('explore')
        yield await self._yield_event("understanding_request", 10)

        user_id = _safe_user_id(context.user_id)
        city = context.new_city or "unknown"
        q = " ".join(context.preferences) if context.preferences else "points of interest"
        
        if user_id > 0:
            asyncio.create_task(self._safe_record_query(user_id, "explore", city, q))

        yield await self._yield_event("fetching_live_data", 30)
        
        # PRIMARY: Get home location anchor
        home_location = context.home_anchor or {"lat": 42.3601, "lng": -71.0589}  # Boston fallback
        lat = home_location.get("lat") if isinstance(home_location, dict) else 42.3601
        lng = home_location.get("lng") if isinstance(home_location, dict) else -71.0589
        
        # Via ProviderManager ONLY
        places_res = await self.provider_manager.search_places(
            query=q,
            lat=lat,
            lng=lng,
            radius=1000,
            limit=20
        )
        
        # Ensure dict structure
        places_res = places_res if isinstance(places_res, dict) else {"results": [], "source": "fallback", "error": "invalid_response"}
        
        # Remap for ranking
        all_places = places_res.get("results", []) or []

        yield await self._yield_event("ranking_results", 60)
        saved = await self._get_saved_refs(context.user_id, "place")

        behavior_weights = {}
        ignored_cats = []
        if user_id > 0:
            try:
                behavior_weights = await self.behavior_tracker.compute_adaptive_weights(user_id)
            except Exception:
                behavior_weights = {}
            try:
                ignored_cats = await self.behavior_tracker.get_ignored_categories(user_id)
            except Exception:
                ignored_cats = []

        try:
            ranked = self.ranking_service.rank_places(
                all_places or [], context,
                saved_item_refs=saved,
                behavior_weights=behavior_weights,
                ignored_categories=ignored_cats,
            )
        except Exception as e:
            logger.error(f"Ranking failed in stream_explore: {e}")
            ranked = []
            
        if ranked:
            RankingService.strip_ranking_metadata(ranked)

        is_fb = places_res.get("source") == "fallback" or places_res.get("error")
        live = [places_res.get("source", "fallback")] if not is_fb else []
        db_src = ["saved_items_db"] if saved else []
        
        if is_fb:
            yield await self._yield_event("fallback_triggered", 90, {"explanation": places_res.get("error", "No data available")})
            metrics.record_fallback("explore")
            if not ranked: metrics.record_empty_state("explore")

        final = APIResponse(
            status="fallback" if is_fb else "success",
            data={"places": ranked or [], "insights": []},
            explanation=places_res.get("error", "") if isinstance(places_res, dict) else "Data fetched successfully",
            context_used={"city": city, "preferences": context.preferences},
            sources=live + db_src if not is_fb else [],
            source_mode="fallback" if is_fb else self._determine_source_mode(live, db_src),
            suggestions=["Try different preferences", "Check saved places"] if is_fb else None,
        )
        await self._log_audit("explore", ["places"], live, db_src, [places_res.get("error", "")] if is_fb else [], context.user_id)
        
        if final.status == "success" and user_id > 0:
            asyncio.create_task(self._update_context_memory(user_id, query=q, domain="explore", city=city, location=context.home_anchor))
            
        if is_fb: final.reason = "provider_fallback"
        yield await self._finalize_stream(final)

    # ─── WORK ───
    async def stream_work(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('work')
        yield await self._yield_event("understanding_request", 10)

        user_id = _safe_user_id(context.user_id)
        city = context.new_city or "unknown"
        job_query = context.work_style or (" ".join(context.preferences[:3]) if context.preferences else "software engineer") or "software engineer"

        if user_id > 0:
            asyncio.create_task(self._safe_record_query(user_id, "work", city, job_query))

        yield await self._yield_event("fetching_live_data", 30)

        # ── Search for coworking spaces via ProviderManager ONLY ──────────
        work_category = "coworking" if context.work_style in ("remote", "hybrid") else "cafe"
        
        work_anchor = context.work_anchor or context.home_anchor or {"lat": 42.3601, "lng": -71.0589}
        lat = work_anchor.get("lat") if isinstance(work_anchor, dict) else 42.3601
        lng = work_anchor.get("lng") if isinstance(work_anchor, dict) else -71.0589
        
        places_res = await self.provider_manager.search_places(
            query=work_category,
            lat=lat,
            lng=lng,
            radius=1000,
            limit=20
        )
        
        # Ensure dict structure
        places_res = places_res if isinstance(places_res, dict) else {"results": [], "source": "fallback", "error": "invalid_response"}
        
        workspaces = places_res.get("results", []) or []

        yield await self._yield_event("ranking_results", 60)
        saved = await self._get_saved_refs(context.user_id, "place")
        anchor = context.work_anchor or context.home_anchor

        behavior_weights, ignored_cats = {}, []
        if user_id > 0:
            try:
                behavior_weights = await self.behavior_tracker.compute_adaptive_weights(user_id)
            except Exception:
                behavior_weights = {}
            try:
                ignored_cats = await self.behavior_tracker.get_ignored_categories(user_id)
            except Exception:
                ignored_cats = []

        try:
            ranked_spaces = self.ranking_service.rank_places(
                workspaces or [], context,
                anchor_location=anchor, saved_item_refs=saved,
                behavior_weights=behavior_weights, ignored_categories=ignored_cats,
            )
        except Exception as e:
            logger.error(f"Ranking failed in stream_work: {e}")
            ranked_spaces = []
            
        if ranked_spaces:
            RankingService.strip_ranking_metadata(ranked_spaces)

        # Determine if fallback
        is_fb = places_res.get("source") == "fallback" or places_res.get("error")
        live_sources = [places_res.get("source", "fallback")] if not is_fb else []

        if is_fb:
            metrics.record_fallback("work")

        final = APIResponse(
            status="fallback" if is_fb else "success",
            data={
                "workspaces": ranked_spaces or [],
                "jobs": [],  # Job search not yet via provider
            },
            explanation=(
                f"Found {len(ranked_spaces)} workspaces."
                if not is_fb
                else places_res.get("error", "No workspaces found")
            ),
            context_used={"city": city, "work_style": context.work_style},
            sources=live_sources,
            source_mode="fallback" if is_fb else self._determine_source_mode(live_sources, []),
            suggestions=["Try exploring cafes", "Check saved workspaces"] if is_fb else None,
        )
        await self._log_audit("work", ["places"], live_sources, [], [], context.user_id)

        if final.status == "success" and user_id > 0:
            asyncio.create_task(self._update_context_memory(user_id, query=job_query, domain="work", city=city, location=anchor))

        if is_fb: final.reason = "provider_fallback"
        yield await self._finalize_stream(final)

    # ─── SERVICES ───
    async def stream_services(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('services')
        yield await self._yield_event("understanding_request", 20)

        user_id = _safe_user_id(context.user_id)
        city = context.new_city or "unknown"
        q = " ".join(context.preferences or ["hospital"])
        
        if user_id > 0:
            asyncio.create_task(self._safe_record_query(user_id, "services", city, q))

        yield await self._yield_event("fetching_live_data", 50)

        # Detect service category from preferences
        category = "hospital"
        for pref in context.preferences or []:
            if not pref or not isinstance(pref, str):
                continue
            p = pref.lower()
            if "pharmacy" in p: category = "pharmacy"
            elif "police" in p: category = "police"
            elif "urgent" in p: category = "urgent_care"
            elif "dentist" in p: category = "dentist"

        # Via ProviderManager ONLY
        home_location = context.home_anchor or {"lat": 42.3601, "lng": -71.0589}
        lat = home_location.get("lat") if isinstance(home_location, dict) else 42.3601
        lng = home_location.get("lng") if isinstance(home_location, dict) else -71.0589
        
        services_res = await self.provider_manager.search_services(
            category=category,
            lat=lat,
            lng=lng,
            radius=1000,
            limit=20
        )
        
        # Ensure dict structure
        services_res = services_res if isinstance(services_res, dict) else {"results": [], "source": "fallback", "error": "invalid_response"}
        
        if services_res.get("error"):
            final = APIResponse(
                status="error", agent="services", source="services_provider", data={"services": []},
                message=services_res.get("error"), reason="provider_error"
            )
            yield await self._finalize_stream(final)
            return

        services_data = services_res.get("results", []) or []
        anchor = context.home_anchor or context.work_anchor
        
        behavior_weights = {}
        ignored_cats = []
        if user_id > 0:
            try:
                behavior_weights = await self.behavior_tracker.compute_adaptive_weights(user_id)
            except Exception:
                behavior_weights = {}
            try:
                ignored_cats = await self.behavior_tracker.get_ignored_categories(user_id)
            except Exception:
                ignored_cats = []

        try:
            services_data = self.ranking_service.rank_services(
                services_data or [], anchor_location=anchor,
                behavior_weights=behavior_weights,
                ignored_categories=ignored_cats,
            ) or []
        except Exception as e:
            logger.error(f"Ranking failed in stream_services: {e}")
            services_data = []
            
        if services_data:
            RankingService.strip_ranking_metadata(services_data)

        final = APIResponse(
            status="success", agent="services", source=services_res.get("source", "fallback"), 
            data={"services": services_data or []},
            message=services_res.get("error", "") or f"Found {len(services_data)} services"
        )
        await self._log_audit("services", ["places"], [services_res.get("source", "fallback")] if services_data else [], [], context.user_id)
        
        if user_id > 0:
            asyncio.create_task(self._update_context_memory(user_id, query=q, domain="services", city=city, location=anchor))
            
        yield await self._finalize_stream(final)

    # ─── CONNECT ───
    async def stream_events(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('events')
        """Alias for stream_connect due to route mismatch."""
        async for chunk in self.stream_connect(context):
            yield chunk

    async def stream_connect(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('connect')
        yield await self._yield_event("understanding_request", 20)

        user_id = _safe_user_id(context.user_id)
        city = context.new_city or "unknown"
        q = " ".join(context.event_categories or context.preferences or ["events"])
        
        if user_id > 0:
            asyncio.create_task(self._safe_record_query(user_id, "connect", city, q))

        yield await self._yield_event("fetching_live_data", 50)

        live_sources, db_sources, all_events = [], [], []

        # Get user-created events from database
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(UserEvent).where(UserEvent.city == city))
                for row in result.scalars():
                    if row and row.id and row.title:
                        all_events.append({
                            "id": str(row.id), "title": row.title,
                            "start_time": str(row.date) if row.date else "",
                            "location": {"name": None, "lat": row.lat, "lng": row.lng},
                            "source_type": "user_created", "source": "user_events_db"
                        })
                if any(e.get("source") == "user_events_db" for e in all_events):
                    db_sources.append("user_events_db")
        except Exception as e:
            logger.debug(f"Error querying user events: {e}")
            pass

        # Via ProviderManager ONLY - search events
        cat = " ".join(context.event_categories) if context.event_categories else ""
        pref_q = " ".join(context.preferences) if context.preferences else ""
        query = f"{cat} {pref_q}".strip() or "events"
        
        events_res = await self.provider_manager.search_events(
            query=query,
            lat=None,
            lng=None,
            radius=10000,
            limit=20
        )
        
        # Ensure dict structure
        events_res = events_res if isinstance(events_res, dict) else {"results": [], "source": "fallback", "error": "invalid_response"}
        
        if events_res.get("results"):
            live_sources.append(events_res.get("source", "events"))
            all_events.extend(events_res.get("results", []) or [])

        saved = await self._get_saved_refs(context.user_id, "event")

        behavior_weights = {}
        ignored_cats = []
        if user_id > 0:
            try:
                behavior_weights = await self.behavior_tracker.compute_adaptive_weights(user_id)
            except Exception:
                behavior_weights = {}
            try:
                ignored_cats = await self.behavior_tracker.get_ignored_categories(user_id)
            except Exception:
                ignored_cats = []

        try:
            ranked = self.ranking_service.rank_events(
                all_events or [], context, saved_item_refs=saved,
                behavior_weights=behavior_weights,
                ignored_categories=ignored_cats,
            ) or []
        except Exception as e:
            logger.error(f"Ranking failed in stream_connect: {e}")
            ranked = []
            
        if ranked:
            RankingService.strip_ranking_metadata(ranked)
            
        sm = self._determine_source_mode(live_sources, db_sources)

        if not ranked:
            metrics.record_fallback("connect")
            metrics.record_empty_state("connect")
            final = APIResponse(
                status="fallback", data={"events": []},
                explanation="No events found locally or via feeds.",
                context_used={"city": city}, sources=[], source_mode="fallback",
                suggestions=["Create a community event", "Try exploring places instead", "Check back later for new events"],
            )
        else:
            final = APIResponse(
                status="success", data={"events": ranked or []},
                explanation=f"Found {len(ranked)} events from {len(live_sources + db_sources)} source(s).",
                context_used={"city": city},
                sources=live_sources + db_sources, source_mode=sm,
            )
        await self._log_audit("connect", ["events"], live_sources, db_sources, [], context.user_id)
        
        if final.status == "success" and user_id > 0:
            asyncio.create_task(self._update_context_memory(user_id, query=q, domain="connect", city=city))
            
        if not ranked: final.reason = "no_events_found"
        yield await self._finalize_stream(final)

    # ─── SETTLE ───
    async def stream_settle_plan(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('settle_plan')
        yield await self._yield_event("understanding_request", 10)
        user_id = _safe_user_id(context.user_id)

        if user_id > 0:
            asyncio.create_task(self._safe_record_query(user_id, "settle", context.new_city, "settle plan"))

        yield await self._yield_event("fetching_live_data", 30)

        live_sources, tasks = [], []
        home_anchor = context.home_anchor or {"lat": 42.3601, "lng": -71.0589}
        lat = home_anchor.get("lat") if isinstance(home_anchor, dict) else 42.3601
        lng = home_anchor.get("lng") if isinstance(home_anchor, dict) else -71.0589

        # ── Via ProviderManager: nearby essentials ─────────────────────────
        for category in ["hospital", "pharmacy", "bank"]:
            services_res = await self.provider_manager.search_services(
                category=category,
                lat=lat,
                lng=lng,
                radius=1000,
                limit=1
            )
            
            services_res = services_res if isinstance(services_res, dict) else {"results": [], "source": "fallback"}
            if services_res.get("results") and len(services_res["results"]) > 0:
                if services_res.get("source") != "fallback" and "places" not in live_sources:
                    live_sources.append(services_res.get("source", "places"))
                top = services_res["results"][0]
                name = top.get("name", "service")
                tasks.append({
                    "category": category,
                    "title": f"Locate nearest {category}: {name}",
                    "detail": f"Address: {top.get('address', 'See map')}",
                    "source": services_res.get("source", "places"),
                })

        # ── Via ProviderManager: neighborhood services ────────────────────
        yield await self._yield_event("merging_outputs", 60)
        for service_type in ["grocery store", "post office"]:
            services_res = await self.provider_manager.search_services(
                category=service_type,
                lat=lat,
                lng=lng,
                radius=1000,
                limit=1
            )
            
            services_res = services_res if isinstance(services_res, dict) else {"results": [], "source": "fallback"}
            if services_res.get("results") and len(services_res["results"]) > 0:
                if services_res.get("source") != "fallback" and services_res.get("source") not in live_sources:
                    live_sources.append(services_res.get("source"))
                top = services_res["results"][0]
                name = top.get("name", service_type)
                tasks.append({
                    "category": service_type,
                    "title": f"Register at nearest {service_type}: {name}",
                    "detail": f"Address: {top.get('address', 'See map')}",
                    "source": services_res.get("source", "places"),
                })

        # ── Always-relevant structural tasks (not hallucinated) ────────────
        tasks.extend([
            {"category": "utilities", "title": "Set up electricity and gas utilities", "detail": "Contact local providers for your address.", "source": "system"},
            {"category": "admin", "title": "Update your address with USPS", "detail": "File a change of address at usps.com/move.", "source": "system"},
            {"category": "housing", "title": "Register for voter registration", "detail": "Update your address at your state election office.", "source": "system"},
        ])

        is_fallback = len(live_sources) == 0
        sm = self._determine_source_mode(live_sources, [])

        if is_fallback:
            metrics.record_fallback("settle")

        final = APIResponse(
            status="fallback" if is_fallback else "success",
            data={"tasks": tasks},
            explanation=(
                f"Generated {len(tasks)} settle tasks from {len(live_sources)} live source(s)."
                if not is_fallback
                else "No live APIs available — returning structural tasks only."
            ),
            context_used={"city": context.new_city, "neighborhood": context.neighborhood},
            sources=live_sources if not is_fallback else [],
            source_mode="fallback" if is_fallback else sm,
            suggestions=["Use Explore to find your neighborhood", "Check Services for healthcare"] if is_fallback else None,
        )
        await self._log_audit("settle", ["places"], live_sources, [], [] if not is_fallback else ["No live APIs"], context.user_id)

        if final.status == "success" and user_id > 0:
            asyncio.create_task(self._update_context_memory(user_id, domain="settle", city=context.new_city))

        yield await self._finalize_stream(final)

    # ─── ASK NATIVE / VOICE ───
    async def stream_voice_query(self, context: UserContext, transcript: str, trace: bool = False) -> AsyncGenerator[str, None]:
        """Full Phase-2 orchestration pipeline with per-yield exception safety."""
        if trace:
            try:
                new_trace('voice')
            except Exception:
                pass

        # ── Helper: safe yield wrapper ────────────────────────────────────
        async def _safe_yield(state: str, progress: int, data: dict = None) -> str:
            try:
                return await self._yield_event(state, progress, data)
            except Exception as e:
                logger.error("_safe_yield failed for state=%s: %s", state, e)
                return safe_emit_event("fallback_triggered", progress, {"error": str(e)})

        yield await _safe_yield("understanding_request", 10)

        # 1. Planner Phase ────────────────────────────────────────────────
        yield await _safe_yield("planner_started", 15)
        try:
            plan = self.planner.generate_plan(transcript)
        except Exception as e:
            logger.error("Planner failed: %s", e)
            from agents.planner import ExecutionPlan, AgentTask
            plan = ExecutionPlan(
                tasks=[AgentTask(agent_name="explore", priority=1)],
                requires_cross_agent=False,
            )

        # Guard: empty plan
        if not plan or not getattr(plan, 'tasks', None):
            from agents.planner import ExecutionPlan, AgentTask
            plan = ExecutionPlan(
                tasks=[AgentTask(agent_name="explore", priority=1)],
                requires_cross_agent=False,
            )

        # Build synthetic context
        try:
            enriched_context = context.model_copy()
            if not enriched_context.preferences:
                enriched_context = context.model_copy(update={"preferences": [transcript]})
        except Exception:
            enriched_context = context

        yield await _safe_yield("routing_agent", 30, {
            "agents": [t.agent_name for t in plan.tasks]
        })

        agent_stream_map = {
            "taste":    self.stream_taste,
            "explore":  self.stream_explore,
            "connect":  self.stream_connect,
            "transit":  self.stream_transit,
            "work":     self.stream_work,
            "services": self.stream_services,
            "settle":   self.stream_settle_plan,
        }

        # 2. Parallel Agent Execution ────────────────────────────────────
        yield await _safe_yield("agent_started", 40)

        async def run_agent(task):
            """Execute a single agent stream — NEVER raises."""
            try:
                stream_fn = agent_stream_map.get(task.agent_name, self.stream_explore)
                last_chunk = None
                async for chunk in stream_fn(enriched_context):
                    last_chunk = chunk
                return last_chunk
            except Exception as e:
                logger.warning("Agent '%s' failed: %s", task.agent_name, e)
                return None

        agent_tasks = [asyncio.create_task(run_agent(t)) for t in plan.tasks]
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)

        # Separate successes from failures
        failed_agents = []
        successful_results = []
        for i, res in enumerate(results):
            agent_name = plan.tasks[i].agent_name if i < len(plan.tasks) else "unknown"
            if isinstance(res, BaseException):
                logger.warning("Agent '%s' raised exception: %s", agent_name, res)
                failed_agents.append(agent_name)
            elif res is None:
                failed_agents.append(agent_name)
            else:
                successful_results.append(res)

        # Emit agent_failed for any failures
        if failed_agents:
            yield await _safe_yield("agent_failed", 55, {"failed_agents": failed_agents})

        yield await _safe_yield("agent_completed", 60)

        # Extract payloads from chunks ───────────────────────────────────
        import json as _json
        agent_payloads = []
        for res_str in successful_results:
            try:
                if res_str and isinstance(res_str, str):
                    res_dict = _json.loads(res_str)
                    if isinstance(res_dict, dict) and res_dict.get("state") == "completed" and "data" in res_dict:
                        agent_payloads.append(res_dict["data"])
            except Exception as e:
                logger.warning("Failed to parse agent result chunk: %s", e)

        # 3. Fusion Engine ───────────────────────────────────────────────
        yield await _safe_yield("fusion_completed", 70)
        fused_data = self.fusion_engine.fuse_results(agent_payloads)

        # 4. Verification Layer ──────────────────────────────────────────
        yield await _safe_yield("verification_completed", 80)
        try:
            ctx_dump = context.model_dump() if hasattr(context, 'model_dump') else {}
            humanized = await self.humanization_service.humanize(fused_data, ctx_dump, "multi_agent")
            humanized = self.verification_service.verify_and_harden(humanized, fused_data)
        except Exception as e:
            logger.error("Humanization/verification failed: %s", e)
            humanized = "Here is the information you requested."

        # 5. Memory Augmentation ─────────────────────────────────────────
        user_id = str(context.user_id) if context.user_id else ""
        if user_id:
            try:
                if self.memory_provider.index is not None:
                    memories = await self.memory_provider.retrieve_relevant_context(user_id, transcript)
                    if memories:
                        fused_data["memory_context"] = [m.content for m in memories]
            except Exception as e:
                logger.warning("Memory retrieval failed (non-fatal): %s", e)

        yield await _safe_yield("humanization_completed", 90)

        # 6. Final Response ──────────────────────────────────────────────
        total_agents = len(plan.tasks)
        successful_count = total_agents - len(failed_agents)

        try:
            final = APIResponse(
                status="success" if fused_data.get("verified", True) else "fallback",
                data=fused_data,
                message=humanized,
                explanation=f"Executed {successful_count}/{total_agents} agents via planner.",
                context_used={"transcript": transcript, "city": context.new_city},
                sources=fused_data.get("sources", []),
                source_mode="live" if fused_data.get("sources") else "fallback",
            )
            payload = final.model_dump()
        except Exception as e:
            logger.error("Final APIResponse construction failed: %s", e)
            payload = {
                "status": "error",
                "data": fused_data,
                "message": humanized,
                "explanation": str(e),
            }

        try:
            if debug := build_debug_block():
                payload["debug"] = debug
        except Exception:
            pass

        yield await _safe_yield("completed", 100, payload)

    # ─── HOME ───
    async def stream_home(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('home')
        yield await self._yield_event("understanding_request", 20)
        
        # Remove city registry dependence - always allow queries
        city = context.new_city or "unknown"
        
        final = APIResponse(
            status="success",
            data={
                "city": city,
                "display_name": city.title(),
                "country_code": "",
                "support_level": "available",  # No city restrictions
                "active_capabilities": {
                    "places": True, "transit": True, "events": True, 
                    "services": True, "work": True
                },
                "active_providers": {
                    "places": "places_provider",
                    "transit": "transit_provider", 
                    "events": "events_provider",
                    "services": "places_provider"
                },
                "partial_notes": {},
                "settle_tasks": [], "connect_events": [], "saved_preview": [],
            },
            explanation=f"Navis is available in {city}. Explore at your own pace.",
            context_used={"city": city}, sources=[], source_mode="system",
        )
        await self._log_audit("home", [], [], [], [], context.user_id)
        yield await self._finalize_stream(final)

    # ─── MOVE ───
    async def stream_move(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('move')
        yield await self._yield_event("understanding_request", 20)
        
        # NO city restrictions - attempt transit search regardless
        yield await self._yield_event("fetching_live_data", 50)
        
        # Try to get transit info via ProviderManager (not yet fully implemented for transit)
        transit_res = await self.provider_manager.search_transit_routes(
            lat=42.3601,  # Boston fallback
            lng=-71.0589,
            limit=10
        )
        
        # Ensure dict structure
        transit_res = transit_res if isinstance(transit_res, dict) else {"results": [], "source": "fallback", "error": "invalid_response"}
        
        if transit_res.get("error") or not transit_res.get("results"):
            final = APIResponse(
                status="fallback", agent="move", source="transit_provider", 
                data={"routes": [], "alerts": [], "stops": []},
                message=transit_res.get("error", "Transit data not available."),
                reason="provider_fallback"
            )
            await self._log_audit("move", ["transit"], [], [], [transit_res.get("error", "")], context.user_id)
            yield await self._finalize_stream(final)
            return

        final = APIResponse(
            status="success", agent="move", source=transit_res.get("source", "transit_provider"),
            data={"routes": transit_res.get("results", []), "alerts": [], "stops": []},
            message=f"Transit routes available in {context.new_city}."
        )
        await self._log_audit("move", ["transit"], [transit_res.get("source")], [], [], context.user_id)
        
        user_id = _safe_user_id(context.user_id)
        if user_id > 0:
            asyncio.create_task(self._update_context_memory(user_id, domain="move", city=context.new_city))
            
        yield await self._finalize_stream(final)

    # ─── SAVED ───
    async def stream_saved(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('saved')
        yield await self._yield_event("fetching_live_data", 50)
        items = []
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(SavedItem).where(SavedItem.user_id == _safe_user_id(context.user_id)))
                for row in result.scalars():
                    items.append({"id": str(row.id), "type": row.item_type, "ref": row.item_ref, "snapshot": row.snapshot, "created_at": str(row.created_at)})
        except Exception:
            pass

        final = APIResponse(
            status="success", data={"saved_items": items},
            explanation=f"Found {len(items)} saved items." if items else "No saved items yet.",
            context_used={"user_id": context.user_id},
            sources=["saved_items_db"], source_mode="mixed",
            suggestions=["Explore places to save", "Check Connect for events to bookmark"] if not items else None,
        )
        await self._log_audit("saved", [], [], ["saved_items_db"], [], context.user_id)
        yield await self._finalize_stream(final)

    # ─── PROFILE ───
    async def stream_profile(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('profile')
        yield await self._yield_event("fetching_live_data", 50)
        final = APIResponse(
            status="success",
            data={"profile": {
                "preferences": context.preferences, "dislikes": context.dislikes,
                "old_city": context.old_city, "new_city": context.new_city,
                "neighborhood": context.neighborhood, "work_area": context.work_area,
                "budget": context.budget, "food_preferences": context.food_preferences,
                "work_style": context.work_style, "mobility_preference": context.mobility_preference,
                "event_categories": context.event_categories,
            }},
            explanation="Read profile from user context.",
            context_used={"user_id": context.user_id},
            sources=["user_profiles_db"], source_mode="mixed",
        )
        await self._log_audit("profile", [], [], ["user_profiles_db"], [], context.user_id)
        yield await self._finalize_stream(final)

    # ─── CROSS-DOMAIN ───
    async def stream_cross_domain(self, context: UserContext, intent: str, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('cross_domain')
        yield await self._yield_event("understanding_request", 10, {"intent": intent})
        il = intent.lower()
        time_anchor = "tonight" if "tonight" in il else "route" if "route" in il else "coffee" if "coffee" in il else "urgent" if "urgent" in il else None

        yield await self._yield_event("fetching_live_data", 30)

        user_id = _safe_user_id(context.user_id)
        home_anchor = context.home_anchor or {"lat": 42.3601, "lng": -71.0589}
        lat = home_anchor.get("lat") if isinstance(home_anchor, dict) else 42.3601
        lng = home_anchor.get("lng") if isinstance(home_anchor, dict) else -71.0589

        if time_anchor == "tonight":
            # Search for events + nearby coworking spaces
            live_sources = []
            
            events_res = await self.provider_manager.search_events(
                query="events",
                lat=lat,
                lng=lng,
                radius=10000,
                limit=5
            )
            
            events_res = events_res if isinstance(events_res, dict) else {"results": [], "source": "fallback"}
            events = events_res.get("results", []) or []
            
            if not events:
                metrics.record_cross_domain(False)
                final = APIResponse(
                    status="fallback", data={"anchor_event": None, "coworking_spaces": []},
                    explanation="No events found tonight.",
                    context_used={"city": context.new_city}, sources=[], source_mode="fallback",
                    suggestions=["Try searching for coworking directly"],
                )
                await self._log_audit("cross_domain", ["events"], [], [], ["no_events"], context.user_id)
                yield await self._finalize_stream(final)
                return

            anchor = events[0]
            if events_res.get("source") != "fallback":
                live_sources.append(events_res.get("source", "events"))
                
            event_loc = anchor.get("location", {})
            yield await self._yield_event("merging_outputs", 60, {"anchor_event_title": anchor.get("title", "Event")})

            # Get coworking spaces via ProviderManager
            work_res = await self.provider_manager.search_places(
                query="coworking",
                lat=lat,
                lng=lng,
                radius=1000,
                limit=10
            )
            
            work_res = work_res if isinstance(work_res, dict) else {"results": [], "source": "fallback"}
            if work_res.get("source") != "fallback":
                live_sources.append(work_res.get("source", "places"))
                
            ranked = []
            if work_res.get("results"):
                ranked = self.ranking_service.rank_places(
                    work_res.get("results", []), context, 
                    anchor_location=event_loc if isinstance(event_loc, dict) else None
                ) or []
                if ranked:
                    RankingService.strip_ranking_metadata(ranked)
            
            metrics.record_cross_domain(bool(ranked))

            final = APIResponse(
                status="success" if ranked else "fallback",
                data={"anchor_event": anchor, "coworking_spaces": ranked[:3]},
                explanation=f"Found event and {len(ranked)} coworking options nearby.",
                context_used={"city": context.new_city}, sources=live_sources,
                source_mode="live" if len(live_sources) >= 1 else "fallback",
            )
            await self._log_audit("cross_domain", ["events", "places"], live_sources, [], [], context.user_id)
            
            if final.status == "success" and user_id > 0:
                asyncio.create_task(self._update_context_memory(user_id, query=intent, domain="cross_domain", city=context.new_city, location=home_anchor))
                
            yield await self._finalize_stream(final)

        elif time_anchor == "route":
            # Find nearby pharmacies
            attempted, live_sources = ["places"], []
            yield await self._yield_event("merging_outputs", 60)
            
            services_res = await self.provider_manager.search_services(
                category="pharmacy",
                lat=lat,
                lng=lng,
                radius=1000,
                limit=5
            )
            
            services_res = services_res if isinstance(services_res, dict) else {"results": [], "source": "fallback"}
            pharmacies = services_res.get("results", []) or []
            
            if services_res.get("source") != "fallback":
                live_sources.append(services_res.get("source", "places"))
                
            if pharmacies:
                anchor = context.home_anchor or context.work_anchor
                pharmacies = self.ranking_service.rank_services(
                    pharmacies, anchor_location=anchor
                ) or []
                if pharmacies:
                    RankingService.strip_ranking_metadata(pharmacies)

            sm = "live" if live_sources else "fallback"
            metrics.record_cross_domain(bool(pharmacies))
            final = APIResponse(
                status="success" if pharmacies else "fallback",
                data={"pharmacies": pharmacies[:3]}, 
                explanation=f"Found {len(pharmacies)} pharmacies near you.",
                context_used={"city": context.new_city}, sources=live_sources, source_mode=sm,
                suggestions=["Try searching services directly"] if not pharmacies else None,
            )
            await self._log_audit("cross_domain", attempted, live_sources, [], [] if pharmacies else ["no_pharmacies"], context.user_id)
            if final.status == "success" and user_id > 0:
                asyncio.create_task(self._update_context_memory(user_id, query=intent, domain="cross_domain", city=context.new_city, location=context.home_anchor))
            yield await self._finalize_stream(final)

        elif time_anchor == "coffee":
            # Find coffee shops
            live_sources = []
            res = await self.provider_manager.search_places(
                query="coffee",
                lat=lat,
                lng=lng,
                radius=1000,
                limit=10
            )
            
            res = res if isinstance(res, dict) else {"results": [], "source": "fallback"}
            if res.get("source") != "fallback":
                live_sources.append(res.get("source", "places"))
                
            saved = await self._get_saved_refs(context.user_id, "place")
            ranked = []
            if res.get("results"):
                ranked = self.ranking_service.rank_places(
                    res.get("results", []), context, 
                    anchor_location=home_anchor, saved_item_refs=saved
                ) or []
                if ranked:
                    RankingService.strip_ranking_metadata(ranked)
                    
            metrics.record_cross_domain(bool(ranked))
            final = APIResponse(
                status="success" if ranked else "fallback", 
                data={"places": ranked[:5]},
                explanation=f"Found {len(ranked)} coffee shops nearby.",
                context_used={"city": context.new_city},
                sources=live_sources, source_mode="live" if live_sources else "fallback",
                suggestions=["Try a different neighborhood"] if not ranked else None,
            )
            await self._log_audit("cross_domain", ["places"], live_sources, [], [], context.user_id)
            if final.status == "success" and user_id > 0:
                asyncio.create_task(self._update_context_memory(user_id, query=intent, domain="cross_domain", city=context.new_city, location=home_anchor))
            yield await self._finalize_stream(final)

        elif time_anchor == "urgent":
            # Find urgent care centers
            attempted, live_sources = ["places"], []
            
            services_res = await self.provider_manager.search_services(
                category="urgent_care",
                lat=lat,
                lng=lng,
                radius=1000,
                limit=5
            )
            
            services_res = services_res if isinstance(services_res, dict) else {"results": [], "source": "fallback"}
            clinics = services_res.get("results", []) or []
            
            if services_res.get("source") != "fallback":
                live_sources.append(services_res.get("source", "places"))
                
            if clinics:
                clinics = self.ranking_service.rank_services(
                    clinics, anchor_location=context.home_anchor
                ) or []
                if clinics:
                    RankingService.strip_ranking_metadata(clinics)
                    
            metrics.record_cross_domain(bool(clinics))
            final = APIResponse(
                status="success" if clinics else "fallback", 
                data={"clinics": clinics[:3]},
                explanation=f"Found {len(clinics)} urgent care options.",
                context_used={"city": context.new_city},
                sources=live_sources, source_mode="live" if live_sources else "fallback",
                suggestions=["Try category: hospital", "Call emergency services if urgent"] if not clinics else None,
            )
            await self._log_audit("cross_domain", attempted, live_sources, [], [] if clinics else ["no_urgent_care"], context.user_id)
            if final.status == "success" and user_id > 0:
                asyncio.create_task(self._update_context_memory(user_id, query=intent, domain="cross_domain", city=context.new_city, location=context.home_anchor))
            yield await self._finalize_stream(final)

        else:
            metrics.record_cross_domain(False)
            final = APIResponse(
                status="fallback", data={}, 
                explanation="Could not parse a supported cross-domain intent.",
                context_used={"intent": intent}, sources=[], source_mode="fallback",
                suggestions=["Try: coworking near tonight's event", "Try: pharmacy near route home", "Try: best coffee near neighborhood"],
            )
            await self._log_audit("cross_domain", [], [], [], ["Unrecognized intent"], context.user_id)
            yield await self._finalize_stream(final)

    # ─── TASTE ───
    async def stream_taste(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('taste')
        yield await self._yield_event("understanding_request", 10)

        user_id = _safe_user_id(context.user_id)
        food_prefs = context.food_preferences or context.preferences or ["restaurant"]
        q = " ".join(food_prefs[:3]) if food_prefs else "restaurant"
        city = context.new_city or "unknown"

        if user_id > 0:
            asyncio.create_task(self._safe_record_query(user_id, "taste", city, q))

        yield await self._yield_event("fetching_live_data", 30)

        # Via ProviderManager ONLY
        home_anchor = context.home_anchor or {"lat": 42.3601, "lng": -71.0589}
        lat = home_anchor.get("lat") if isinstance(home_anchor, dict) else 42.3601
        lng = home_anchor.get("lng") if isinstance(home_anchor, dict) else -71.0589
        
        places_res = await self.provider_manager.search_places(
            query=q,
            lat=lat,
            lng=lng,
            radius=1000,
            limit=20
        )
        
        # Ensure dict structure
        places_res = places_res if isinstance(places_res, dict) else {"results": [], "source": "fallback", "error": "invalid_response"}
        
        all_places = places_res.get("results", []) or []

        yield await self._yield_event("ranking_results", 60)

        saved = await self._get_saved_refs(context.user_id, "place")
        live_sources = [places_res.get("source", "fallback")] if places_res.get("source") != "fallback" else []

        behavior_weights = {}
        ignored_cats = []
        if user_id > 0:
            try:
                behavior_weights = await self.behavior_tracker.compute_adaptive_weights(user_id)
            except Exception:
                behavior_weights = {}
            try:
                ignored_cats = await self.behavior_tracker.get_ignored_categories(user_id)
            except Exception:
                ignored_cats = []

        try:
            ranked = self.ranking_service.rank_places(
                all_places or [], context,
                saved_item_refs=saved,
                behavior_weights=behavior_weights,
                ignored_categories=ignored_cats,
            ) or []
        except Exception as e:
            logger.error(f"Ranking failed in stream_taste: {e}")
            ranked = []

        if ranked:
            RankingService.strip_ranking_metadata(ranked)

        is_fb = places_res.get("source") == "fallback" or places_res.get("error")
        db_src = ["saved_items_db"] if saved else []

        if is_fb:
            yield await self._yield_event("fallback_triggered", 90, {"explanation": places_res.get("error", "No restaurants found")})
            metrics.record_fallback("taste")
            if not ranked:
                metrics.record_empty_state("taste")

        final = APIResponse(
            status="fallback" if is_fb else "success",
            data={"restaurants": ranked or [], "insights": []},
            explanation=places_res.get("error", "") if isinstance(places_res, dict) else "Restaurants found",
            context_used={"city": city, "food_preferences": food_prefs},
            sources=live_sources + db_src if not is_fb else [],
            source_mode="fallback" if is_fb else self._determine_source_mode(live_sources, db_src),
            suggestions=["Try different preferences", "Check saved restaurants"] if is_fb else None,
        )
        await self._log_audit("taste", ["places"], live_sources, db_src, [places_res.get("error", "")] if is_fb else [], context.user_id)

        if final.status == "success" and user_id > 0:
            asyncio.create_task(self._update_context_memory(user_id, query=q, domain="taste", city=city, location=context.home_anchor))

        if is_fb:
            final.reason = "provider_fallback"
        yield await self._finalize_stream(final)

    # ─── TRANSIT ───
    async def stream_transit(self, context: UserContext, trace: bool = False) -> AsyncGenerator[str, None]:
        if trace: new_trace('transit')
        """Dedicated transit stream via ProviderManager."""
        yield await self._yield_event("understanding_request", 20)

        # NO city restrictions - attempt transit search regardless
        yield await self._yield_event("fetching_live_data", 50)
        
        # Via ProviderManager ONLY
        transit_res = await self.provider_manager.search_transit_routes(
            lat=42.3601,  # Boston fallback
            lng=-71.0589,
            limit=10
        )
        
        transit_res = transit_res if isinstance(transit_res, dict) else {"results": [], "source": "fallback", "error": "invalid_response"}

        if transit_res.get("error") or not transit_res.get("results"):
            final = APIResponse(
                status="fallback", agent="transit", source="transit_provider", 
                data={"routes": [], "alerts": [], "stops": []},
                message=transit_res.get("error", "Transit data not available."),
                reason="provider_fallback"
            )
            await self._log_audit("transit", ["transit"], [], [], [transit_res.get("error", "")], context.user_id)
            yield await self._finalize_stream(final)
            return

        final = APIResponse(
            status="success", agent="transit", source=transit_res.get("source", "transit_provider"),
            data={
                "routes": transit_res.get("results", []),
                "alerts": [],
                "stops": [],
                "provider": transit_res.get("source", "transit_provider"),
            },
            message=f"Live transit data available."
        )
        await self._log_audit("transit", ["transit"], [transit_res.get("source")], [], [], context.user_id)

        user_id = _safe_user_id(context.user_id)
        if user_id > 0:
            asyncio.create_task(self._update_context_memory(
                user_id, domain="transit", city=context.new_city
            ))

        yield await self._finalize_stream(final)
