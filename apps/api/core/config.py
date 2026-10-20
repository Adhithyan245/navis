import os
from pathlib import Path
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve apps/api/.env from THIS FILE's location, not the CWD. Previously
# `env_file=".env"` (relative) — pydantic-settings looked for ./.env in
# whatever directory uvicorn was launched from, so when running from the
# repo root every API key silently became `None`. Compute the absolute
# path here so loading is location-independent.
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    # API Keys
    OPENROUTESERVICE_API_KEY: Optional[str] = None
    GEOAPIFY_API_KEY: Optional[str] = None
    FOURSQUARE_API_KEY: Optional[str] = None
    TICKETMASTER_API_KEY: Optional[str] = None
    EVENTBRITE_API_KEY: Optional[str] = None
    MAPTILER_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    HUGGINGFACE_API_KEY: Optional[str] = None

    # LLM models. Groq retires models regularly (llama-3.3-70b-versatile now
    # 404s with model_not_found), so keep these overridable from .env.
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    HUGGINGFACE_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"
    # Small, fast model for latency-sensitive helpers (location acronym expansion).
    GROQ_FAST_MODEL: str = "openai/gpt-oss-20b"
    # Speech-to-text for POST /v2/voice (Groq Whisper).
    GROQ_STT_MODEL: str = "whisper-large-v3-turbo"

    # Auth: shared secret the Next.js server sends to /v2/auth/* (never the
    # browser), and where account records live.
    AUTH_INTERNAL_SECRET: Optional[str] = None
    ACCOUNTS_DB_PATH: Optional[str] = None
    # Postgres for accounts + synced data (postgresql://...). Unset → SQLite file.
    ACCOUNTS_DATABASE_URL: Optional[str] = None

    # Shared cache + rate limits across workers/instances (redis://...).
    # Unset → per-process memory (fine for one instance).
    REDIS_URL: Optional[str] = None
    CACHE_MAX_ENTRIES: int = 5000

    # Signed short-lived tokens the Next server mints for signed-in users;
    # costly routes (AI, voice, place lookups) require one. Defaults to
    # required in production. The key defaults to one derived from
    # AUTH_INTERNAL_SECRET.
    API_TOKEN_SECRET: Optional[str] = None
    REQUIRE_API_TOKEN: Optional[bool] = None

    # Geocoding / place search. The public OSM instance allows ~1 req/s;
    # point at your own Nominatim and set the interval to 0 to scale.
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_MIN_INTERVAL_S: float = 1.05
    # Public transit routing (MOTIS / Transitous-compatible API).
    TRANSIT_ROUTING_URL: str = "https://api.transitous.org"

    # Push notifications. Android: Firebase Cloud Messaging (HTTP v1) with a
    # service-account JSON (inline or a file path). iOS: APNs token auth (.p8).
    FCM_PROJECT_ID: Optional[str] = None
    FCM_SERVICE_ACCOUNT_JSON: Optional[str] = None
    APNS_KEY_ID: Optional[str] = None
    APNS_TEAM_ID: Optional[str] = None
    APNS_PRIVATE_KEY: Optional[str] = None
    APNS_BUNDLE_ID: Optional[str] = None
    APNS_USE_SANDBOX: bool = False

    # App Config
    ENV: str = "development"
    # Off unless explicitly enabled: debug mode returns tracebacks to clients.
    DEBUG: bool = False
    PORT: int = 8100

    # CORS — comma-separated origin list. Wildcard `*` with credentials=True
    # is forbidden by the CORS spec; production deployments MUST set this
    # explicitly to their public frontend origins.
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Resiliency
    GLOBAL_TIMEOUT: int = 10
    MAX_CONCURRENCY: int = 20

    @field_validator("ACCOUNTS_DATABASE_URL", "REDIS_URL", mode="before")
    @classmethod
    def _clean_url(cls, value):
        """Accept connection strings pasted straight from provider dashboards:
        `REDIS_URL="rediss://..."`, `psql 'postgresql://...'`, stray quotes."""
        if not isinstance(value, str):
            return value
        v = value.strip()
        if v.lower().startswith("psql "):
            v = v[5:].strip()
        if "=" in v.split("://", 1)[0]:
            v = v.split("=", 1)[1].strip()
        v = v.strip("'\"").strip()
        return v or None

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Exposed so /providers/diagnostics can report which file was actually used
# (for env-loading debugging).
ENV_FILE_PATH: str = str(_ENV_FILE)
ENV_FILE_EXISTS: bool = _ENV_FILE.exists()

settings = Settings()


def is_production() -> bool:
    return settings.ENV.lower() in ("production", "prod", "staging")


def api_token_required() -> bool:
    if settings.REQUIRE_API_TOKEN is not None:
        return settings.REQUIRE_API_TOKEN
    return is_production()
