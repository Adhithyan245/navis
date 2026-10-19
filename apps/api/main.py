"""
main.py — Navis Orchestration API

Lifespan:
  1. Create shared aiohttp TCPConnector + ClientSession
  2. Inject session into ProviderManager
  3. Run provider credential validation (non-blocking)
  4. Start profiling daemon (loop-lag, memory, task-leak)
  5. Start provider revalidation background task
  6. Yield (serve requests)
  7. Drain and teardown on SIGTERM
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import aiohttp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import ENV_FILE_EXISTS, ENV_FILE_PATH, settings
from apps.api.core.middleware import TraceIDMiddleware, SchemaEnforcementMiddleware
from apps.api.core.security import (
    PayloadSizeMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware, StreamAbuseMiddleware,
)
from apps.api.core.logging import setup_logging, get_logger
from apps.api.routes import health, onboard, interaction, providers, workflow, query, voice, geocode, events, auth, agents, today, maps, push
from apps.api.services.provider_manager import provider_manager
from apps.api.services.provider_validator import run_validation, start_revalidation_task
from apps.api.observability.profiling import start_profiling_daemon

# Importing apps.api.runtime.nodes triggers @register decorators so every
# built-in node type is in the NodeRegistry before workflows are compiled.
import apps.api.runtime.nodes  # noqa: F401
from apps.api.runtime.compiler.registry import workflow_registry
from apps.api.services.context_retriever import context_retriever

setup_logging()
logger = get_logger(__name__)


_DIAGNOSTIC_KEYS = (
    "OPENROUTESERVICE_API_KEY",
    "GEOAPIFY_API_KEY",
    "FOURSQUARE_API_KEY",
    "TICKETMASTER_API_KEY",
    "EVENTBRITE_API_KEY",
    "MAPTILER_API_KEY",
    "GROQ_API_KEY",
    "HUGGINGFACE_API_KEY",
)


def _log_env_summary() -> None:
    """Visible startup line listing exactly which API keys were detected.

    The previous behaviour silently produced None for every key when the
    .env path resolved wrong — leading to "invalid_credentials" verdicts
    that masked a config-loading bug. This summary makes that class of
    failure obvious in the first 10 lines of startup.
    """
    configured = [k for k in _DIAGNOSTIC_KEYS if getattr(settings, k, None)]
    missing = [k for k in _DIAGNOSTIC_KEYS if not getattr(settings, k, None)]
    logger.info(
        "env summary",
        env_file=ENV_FILE_PATH,
        env_file_exists=ENV_FILE_EXISTS,
        configured_keys=len(configured),
        missing_keys=len(missing),
        configured=configured,
        missing=missing,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log_env_summary()

    # ── 1. Shared aiohttp session pool ────────────────────────────────────────
    connector = aiohttp.TCPConnector(
        limit=settings.MAX_CONCURRENCY,
        limit_per_host=10,
        enable_cleanup_closed=True,
    )
    timeout = aiohttp.ClientTimeout(total=settings.GLOBAL_TIMEOUT)
    session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    # ── 2. Inject into ProviderManager ────────────────────────────────────────
    provider_manager.set_session(session)
    logger.info("aiohttp session pool initialised", concurrency=settings.MAX_CONCURRENCY)
    
    # ── Start behavior queue worker ──────────────────────────────────────────
    from apps.api.services.behavior_queue import behavior_queue
    behavior_queue.start()

    # ── 3. Non-blocking provider validation ───────────────────────────────────
    try:
        states = await run_validation(session)
        healthy = sum(1 for v in states.values() if v["status"] == "healthy")
        logger.info("Provider validation complete", healthy=healthy, total=len(states))
    except Exception as e:
        logger.error("Provider validation error (non-fatal)", error=str(e))

    # ── 4. Profiling daemon ───────────────────────────────────────────────────
    await start_profiling_daemon()

    # ── 5. Background revalidation task ───────────────────────────────────────
    revalidation_task = start_revalidation_task(lambda: session)

    # ── 6. Load markdown knowledge corpus ─────────────────────────────────────
    try:
        kn = context_retriever.load("knowledge")
        logger.info("knowledge corpus loaded", chunks=kn)
    except Exception as e:
        logger.error("knowledge corpus load failed (non-fatal)", error=str(e))

    # ── 7. Compile workflow definitions ───────────────────────────────────────
    try:
        loaded = workflow_registry.load_dir("apps/api/workflows")
        logger.info("workflows loaded", count=loaded, names=list(workflow_registry.names()))
    except Exception as e:
        logger.error("workflow registry load failed (non-fatal)", error=str(e))

    yield  # ── Serve requests ─────────────────────────────────────────────────

    # ── 6. Graceful shutdown ──────────────────────────────────────────────────
    logger.info("Shutting down Navis — draining connections")
    from apps.api.services.behavior_queue import behavior_queue
    await behavior_queue.stop()
    from apps.api.core.background import background_task_manager
    await background_task_manager.cancel_all()
    revalidation_task.cancel()
    await session.close()
    await connector.close()
    from apps.api.core.http import close_sessions
    await close_sessions()
    logger.info("Shutdown complete")




app = FastAPI(
    title="Navis Orchestration API",
    description="Multi-agent urban intelligence orchestration platform.",
    version="2.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Middleware (inner → outer = last added runs first)
app.add_middleware(StreamAbuseMiddleware)
app.add_middleware(SchemaEnforcementMiddleware)
# Size cap wraps everything that reads the body; rate limits run before it.
app.add_middleware(PayloadSizeMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TraceIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
# CORS — explicit origin allowlist. Wildcard `*` with credentials=True is a
# CORS spec violation (browsers correctly reject it) and was the prior config.
# Override via the CORS_ALLOW_ORIGINS env var (comma-separated) in deployment.
_cors_origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
logger.info("CORS allowlist", origins=_cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-Trace-Id"],
    expose_headers=["X-Trace-Id"],
    max_age=600,
)

# Routers
app.include_router(health.router,       tags=["Health"])
app.include_router(onboard.router,      tags=["Onboarding"])
app.include_router(interaction.router,  tags=["Interaction"])
app.include_router(providers.router,    tags=["Providers"])
app.include_router(workflow.router,     tags=["Workflow Runtime"])
app.include_router(query.router,        tags=["Query Runtime"])
app.include_router(voice.router,        tags=["Voice Transport"])
app.include_router(geocode.router,      tags=["Geocoding"])
app.include_router(events.router,       tags=["Events"])
app.include_router(auth.router,         tags=["Auth"])
app.include_router(agents.router,       tags=["Agents"])
app.include_router(today.router,        tags=["Today hub"])
app.include_router(maps.router,         tags=["Maps & care"])
app.include_router(push.router,         tags=["Push"])
