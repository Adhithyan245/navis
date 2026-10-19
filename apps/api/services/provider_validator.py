"""
services/provider_validator.py

Validates all API keys and provider connectivity on startup.
Never crashes the server on failure — marks providers degraded/offline instead.

Provider states:
  healthy              — provider reachable + auth accepted
  degraded             — reachable but returning non-2xx (other than auth)
  not_configured       — no API key is set in apps/api/.env for this provider
  invalid_credentials  — key IS set but the provider rejected it (HTTP 401/403)
  quota_exceeded       — HTTP 429
  timeout              — request didn't return in time
  offline              — network error reaching the provider

`not_configured` is intentionally distinct from `invalid_credentials` so the
UI can tell the operator "add the key" vs "the key is wrong/revoked".
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Any, Optional

from apps.api.core.config import settings
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

REVALIDATION_INTERVAL = 900  # 15 minutes

_provider_states: Dict[str, Dict[str, Any]] = {}


def _state(status: str, latency_ms: float = 0.0, note: str = "", fallback: bool = True) -> Dict[str, Any]:
    return {
        "status": status,
        "latency_ms": round(latency_ms, 1),
        "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": note,
        "fallback_available": fallback,
        "quota_warning": False,
    }


async def _ping(session, url: str, *, method: str = "GET", headers: Dict = None,
                json_body: Dict = None, timeout: float = 6.0) -> tuple[int, float]:
    """Returns (http_status, latency_ms). Raises on network error."""
    import aiohttp
    t0 = time.monotonic()
    async with session.request(
        method, url,
        headers=headers or {},
        json=json_body,
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        latency = (time.monotonic() - t0) * 1000
        return resp.status, latency


async def _validate_nominatim(session) -> Dict:
    try:
        status, ms = await _ping(
            session,
            "https://nominatim.openstreetmap.org/search?q=Paris&format=json&limit=1",
            headers={"User-Agent": "NavisValidator/1.0"},
        )
        return _state("healthy", ms) if status == 200 else _state("degraded", ms, f"HTTP {status}")
    except asyncio.TimeoutError:
        return _state("timeout", note="Nominatim timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _validate_mediawiki(session) -> Dict:
    try:
        status, ms = await _ping(
            session, "https://en.wikipedia.org/api/rest_v1/page/summary/Paris",
            headers={"User-Agent": "NavisValidator/1.0"},
        )
        return _state("healthy", ms) if status == 200 else _state("degraded", ms, f"HTTP {status}")
    except asyncio.TimeoutError:
        return _state("timeout", note="MediaWiki timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _validate_geoapify(session) -> Dict:
    if not settings.GEOAPIFY_API_KEY:
        return _state("not_configured", note="API key not set in apps/api/.env")
    try:
        url = f"https://api.geoapify.com/v1/geocode/search?text=Paris&limit=1&apiKey={settings.GEOAPIFY_API_KEY}"
        status, ms = await _ping(session, url)
        if status == 200:
            return _state("healthy", ms)
        if status in (401, 403):
            return _state("invalid_credentials", ms, f"HTTP {status}")
        if status == 429:
            s = _state("quota_exceeded", ms, "Rate limited"); s["quota_warning"] = True; return s
        return _state("degraded", ms, f"HTTP {status}")
    except asyncio.TimeoutError:
        return _state("timeout", note="Geoapify timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _validate_foursquare(session) -> Dict:
    if not settings.FOURSQUARE_API_KEY:
        return _state("not_configured", note="API key not set in apps/api/.env")
    from apps.api.services.providers.places import FOURSQUARE_API_VERSION, FOURSQUARE_SEARCH_URL
    try:
        url = f"{FOURSQUARE_SEARCH_URL}?ll=48.8566,2.3522&limit=1"
        status, ms = await _ping(session, url, headers={
            "Authorization": f"Bearer {settings.FOURSQUARE_API_KEY}",
            "X-Places-Api-Version": FOURSQUARE_API_VERSION,
        })
        if status == 200:
            return _state("healthy", ms)
        if status in (401, 403):
            return _state("invalid_credentials", ms, f"HTTP {status}")
        if status == 429:
            s = _state("quota_exceeded", ms); s["quota_warning"] = True; return s
        return _state("degraded", ms, f"HTTP {status}")
    except asyncio.TimeoutError:
        return _state("timeout", note="Foursquare timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _validate_ticketmaster(session) -> Dict:
    if not settings.TICKETMASTER_API_KEY:
        return _state("not_configured", note="API key not set in apps/api/.env")
    try:
        url = f"https://app.ticketmaster.com/discovery/v2/events.json?size=1&apikey={settings.TICKETMASTER_API_KEY}"
        status, ms = await _ping(session, url)
        if status == 200:
            return _state("healthy", ms)
        if status in (401, 403):
            return _state("invalid_credentials", ms, f"HTTP {status}")
        if status == 429:
            s = _state("quota_exceeded", ms); s["quota_warning"] = True; return s
        return _state("degraded", ms, f"HTTP {status}")
    except asyncio.TimeoutError:
        return _state("timeout", note="Ticketmaster timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _probe_completion(session, url: str, api_key: str, model: str,
                            timeout: float = 15.0) -> tuple[int, float, str]:
    """POST a tiny chat completion. Returns (http_status, latency_ms, text).
    A provider is only healthy if it can actually complete with the
    configured model — listing /models succeeds even when the model 404s."""
    import aiohttp
    from apps.api.services.providers.ai import extract_chat_text
    t0 = time.monotonic()
    async with session.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": "Reply with OK."}]},
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as resp:
        latency = (time.monotonic() - t0) * 1000
        text = ""
        if resp.status == 200:
            try:
                text = extract_chat_text(await resp.json())
            except Exception:
                text = ""
        return resp.status, latency, text


def _completion_state(name: str, status: int, ms: float, text: str, model: str) -> Dict:
    if status == 200:
        if text:
            return _state("healthy", ms, f"model {model}")
        return _state("degraded", ms, f"{model} returned an empty completion")
    if status in (401, 403):
        note = f"HTTP {status}"
        if name == "huggingface" and status == 403:
            note = "Token lacks the 'Inference Providers' permission"
        return _state("invalid_credentials", ms, note)
    if status == 404:
        return _state("degraded", ms, f"model {model} not available (HTTP 404)")
    if status == 429:
        s = _state("quota_exceeded", ms, "Rate limited"); s["quota_warning"] = True; return s
    return _state("degraded", ms, f"HTTP {status}")


async def _validate_groq(session) -> Dict:
    if not settings.GROQ_API_KEY:
        return _state("not_configured", note="API key not set in apps/api/.env")
    from apps.api.services.providers.ai import GROQ_CHAT_URL
    try:
        status, ms, text = await _probe_completion(
            session, GROQ_CHAT_URL, settings.GROQ_API_KEY, settings.GROQ_MODEL)
        return _completion_state("groq", status, ms, text, settings.GROQ_MODEL)
    except asyncio.TimeoutError:
        return _state("timeout", note="Groq timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _validate_huggingface(session) -> Dict:
    if not settings.HUGGINGFACE_API_KEY:
        return _state("not_configured", note="API key not set in apps/api/.env")
    from apps.api.services.providers.ai import HF_CHAT_URL
    try:
        status, ms, text = await _probe_completion(
            session, HF_CHAT_URL, settings.HUGGINGFACE_API_KEY, settings.HUGGINGFACE_MODEL)
        return _completion_state("huggingface", status, ms, text, settings.HUGGINGFACE_MODEL)
    except asyncio.TimeoutError:
        return _state("timeout", note="HuggingFace timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _validate_openrouteservice(session) -> Dict:
    if not settings.OPENROUTESERVICE_API_KEY:
        return _state("not_configured", note="API key not set in apps/api/.env")
    try:
        # ORS has no /v2/health; probe a tiny real route instead.
        url = ("https://api.openrouteservice.org/v2/directions/driving-car"
               "?start=2.3522,48.8566&end=2.3600,48.8600")
        status, ms = await _ping(session, url, headers={"Authorization": settings.OPENROUTESERVICE_API_KEY})
        if status in (200, 204):
            return _state("healthy", ms)
        if status in (401, 403):
            return _state("invalid_credentials", ms, f"HTTP {status}")
        if status in (502, 503, 504):
            return _state("degraded", ms, f"ORS service unavailable (HTTP {status})")
        return _state("degraded", ms, f"HTTP {status}")
    except asyncio.TimeoutError:
        return _state("timeout", note="ORS timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def _validate_eventbrite(session) -> Dict:
    if not settings.EVENTBRITE_API_KEY:
        return _state("not_configured", note="API key not set in apps/api/.env")
    try:
        url = "https://www.eventbriteapi.com/v3/users/me/"
        status, ms = await _ping(session, url, headers={"Authorization": f"Bearer {settings.EVENTBRITE_API_KEY}"})
        if status == 200:
            # The key works, but Eventbrite retired location search, so it
            # can't serve as an events fallback.
            return _state("degraded", ms, "Key valid; Eventbrite retired public event search",
                          fallback=False)
        if status in (401, 403):
            return _state("invalid_credentials", ms, f"HTTP {status}")
        return _state("degraded", ms, f"HTTP {status}")
    except asyncio.TimeoutError:
        return _state("timeout", note="Eventbrite timed out")
    except Exception as e:
        return _state("offline", note=str(e))


async def run_validation(session) -> Dict[str, Dict]:
    """
    Runs all provider validations concurrently with return_exceptions=True.
    Always returns a full status dict — never raises.
    """
    validators = {
        "nominatim":         _validate_nominatim(session),
        "mediawiki":         _validate_mediawiki(session),
        "geoapify":          _validate_geoapify(session),
        "foursquare":        _validate_foursquare(session),
        "ticketmaster":      _validate_ticketmaster(session),
        "groq":              _validate_groq(session),
        "huggingface":       _validate_huggingface(session),
        "openrouteservice":  _validate_openrouteservice(session),
        "eventbrite":        _validate_eventbrite(session),
    }

    results = await asyncio.gather(*validators.values(), return_exceptions=True)
    states: Dict[str, Dict] = {}
    for name, result in zip(validators.keys(), results):
        if isinstance(result, Exception):
            states[name] = _state("offline", note=str(result))
        else:
            states[name] = result
        logger.info("Provider validated", provider=name, status=states[name]["status"])

    global _provider_states
    _provider_states = states
    return states


def get_provider_states() -> Dict[str, Dict]:
    return _provider_states


async def _revalidation_loop(session_getter) -> None:
    """Background revalidation every REVALIDATION_INTERVAL seconds."""
    while True:
        await asyncio.sleep(REVALIDATION_INTERVAL)
        try:
            session = session_getter()
            if session:
                logger.info("Running periodic provider revalidation")
                await run_validation(session)
        except Exception as e:
            logger.error("Provider revalidation failed", error=str(e))


def start_revalidation_task(session_getter) -> asyncio.Task:
    return asyncio.create_task(
        _revalidation_loop(session_getter),
        name="navis-provider-revalidation"
    )
