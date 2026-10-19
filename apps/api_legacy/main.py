import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.middleware import GlobalResponseValidationMiddleware
from core.schema_enforcement import SchemaEnforcementMiddleware
from core.config import settings
from core.logging_config import configure_logging
from routes import (
    health, onboard, settle, explore, work, services, connect,
    home, move, saved, profile, ops, interaction, agents,
    taste, voice, transit,
)

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="OLAA / Native API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Phase 2: Schema enforcement middleware (validates all responses)
app.add_middleware(SchemaEnforcementMiddleware)
# Existing: Global response validation middleware
app.add_middleware(GlobalResponseValidationMiddleware)

# ── Route registration ────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(onboard.router)
app.include_router(settle.router)
app.include_router(explore.router)
app.include_router(work.router)
app.include_router(services.router)
app.include_router(connect.router)
app.include_router(home.router)
app.include_router(move.router)
app.include_router(saved.router)
app.include_router(profile.router)
app.include_router(ops.router)
app.include_router(interaction.router)
app.include_router(agents.router)
# ── New / restored agents ─────────────────────────────────────────────────────
app.include_router(taste.router)
app.include_router(voice.router)
app.include_router(transit.router)


@app.on_event("startup")
async def startup_event():
    """Log API key status at startup so missing keys are immediately visible."""
    logger.info("Navis API v2.1.0 starting — active providers: %s", settings.active_providers())
    settings.validate_api_dependencies()
