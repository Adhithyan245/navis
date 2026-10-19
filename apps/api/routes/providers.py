"""routes/providers.py — Provider health, validation state, budget metrics, and key diagnostics."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from apps.api.core.ops import require_ops

from apps.api.core.config import ENV_FILE_EXISTS, ENV_FILE_PATH, settings
from apps.api.services.provider_validator import get_provider_states
from apps.api.services.provider_budget import provider_budget

router = APIRouter(dependencies=[Depends(require_ops)])


# Keys reported by /providers/diagnostics. Add new ones here when a new
# provider is wired up so the diagnostics endpoint stays the canonical
# "is everything configured?" view.
_DIAGNOSTIC_KEYS: List[str] = [
    "OPENROUTESERVICE_API_KEY",
    "GEOAPIFY_API_KEY",
    "FOURSQUARE_API_KEY",
    "TICKETMASTER_API_KEY",
    "EVENTBRITE_API_KEY",
    "MAPTILER_API_KEY",
    "GROQ_API_KEY",
    "HUGGINGFACE_API_KEY",
]


@router.get("/providers/status")
async def provider_status():
    """
    Returns current health state for each provider, including:
    - validation status (healthy / degraded / invalid_credentials / ...)
    - last checked timestamp
    - latency
    - fallback availability
    - quota warnings
    """
    return get_provider_states()


@router.get("/providers/metrics")
async def provider_metrics():
    """
    Returns per-provider usage budget metrics:
    - daily calls used/remaining
    - per-minute limit
    - quota warning flag
    """
    return provider_budget.get_metrics()


@router.get("/providers/budget")
async def provider_budget_detail():
    """Detailed budget view with per-minute + daily counters."""
    states  = get_provider_states()
    budgets = provider_budget.get_metrics()
    merged = {}
    for name in set(list(states.keys()) + list(budgets.keys())):
        merged[name] = {
            "health":  states.get(name, {}),
            "budget":  budgets.get(name, {}),
        }
    return merged


@router.get("/providers/diagnostics")
async def provider_diagnostics() -> Dict[str, Any]:
    """
    Per-key configuration diagnostics. Tells you which API keys actually
    loaded into Settings, where the .env file was resolved from, and
    whether each key is present (NEVER returns the key itself — only
    length + a one-char prefix for cross-checking).

    Use this to distinguish "key isn't being loaded" (a config/path bug)
    from "key was rejected by the upstream provider" (a credential bug).
    The two were previously indistinguishable in /providers/status.
    """
    keys: Dict[str, Dict[str, Any]] = {}
    for name in _DIAGNOSTIC_KEYS:
        value = getattr(settings, name, None)
        if value:
            keys[name] = {
                "configured": True,
                "length": len(value),
                "prefix": value[:1] + "...",  # one char only; lets ops spot which key it is without leaking it
            }
        else:
            keys[name] = {
                "configured": False,
                "length": 0,
                "prefix": None,
            }

    return {
        "env_file": {
            "path": ENV_FILE_PATH,
            "exists": ENV_FILE_EXISTS,
        },
        "keys": keys,
        "summary": {
            "total": len(_DIAGNOSTIC_KEYS),
            "configured": sum(1 for k in keys.values() if k["configured"]),
            "missing": sum(1 for k in keys.values() if not k["configured"]),
        },
    }
