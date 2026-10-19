"""
Adzuna Jobs API service — powers Work agent job listings.

Free tier: 250 requests/day.
Get credentials: https://developer.adzuna.com

Activated only when ADZUNA_APP_ID and ADZUNA_APP_KEY are both set.
Falls back gracefully when keys are missing.
"""

import time
import httpx
from typing import Dict, Any
from core.config import settings
from services.cache import cache_get, cache_set
from services.metrics import metrics

# Adzuna uses country codes in the URL path
_COUNTRY_MAP = {
    "us": "us", "usa": "us", "united states": "us",
    "gb": "gb", "uk": "gb", "united kingdom": "gb",
    "ca": "ca", "canada": "ca",
    "au": "au", "australia": "au",
    "de": "de", "germany": "de",
    "fr": "fr", "france": "fr",
}

def _country_code(city: str) -> str:
    """Best-effort country detection from city string. Defaults to 'us'."""
    lower = city.lower()
    for keyword, code in _COUNTRY_MAP.items():
        if keyword in lower:
            return code
    return "us"


from core.dependencies import assert_api_available

class AdzunaService:
    BASE_URL = "https://api.adzuna.com/v1/api/jobs"
    REQUIRED_API = "adzuna"

    async def search_jobs(
        self,
        query: str,
        city: str,
        results_per_page: int = 10,
    ) -> Dict[str, Any]:
        assert_api_available(self.REQUIRED_API)

        cache_key = f"{query}|{city}"
        cached = cache_get("adzuna", city, cache_key)
        if cached is not None:
            return cached

        country = _country_code(city)
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.BASE_URL}/{country}/search/1",
                    params={
                        "app_id": settings.adzuna_app_id,
                        "app_key": settings.adzuna_app_key,
                        "results_per_page": results_per_page,
                        "what": query,
                        "where": city,
                        "content-type": "application/json",
                    },
                )
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    raw_jobs = res.json().get("results", [])
                    normalized = []
                    for job in raw_jobs:
                        salary_min = job.get("salary_min")
                        salary_max = job.get("salary_max")
                        salary_str = None
                        if salary_min and salary_max:
                            salary_str = f"${salary_min:,.0f} – ${salary_max:,.0f}"
                        elif salary_min:
                            salary_str = f"${salary_min:,.0f}+"

                        normalized.append({
                            "id": job.get("id", ""),
                            "title": job.get("title", ""),
                            "company": job.get("company", {}).get("display_name", ""),
                            "location": job.get("location", {}).get("display_name", city),
                            "salary": salary_str,
                            "description": job.get("description", "")[:300],  # Truncate for response size
                            "url": job.get("redirect_url", ""),
                            "created": job.get("created", ""),
                            "source": "adzuna",
                        })

                    result = {
                        "status": "success",
                        "jobs": normalized,
                        "explanation": (
                            f"Found {len(normalized)} jobs via Adzuna."
                            if normalized
                            else "Adzuna returned no jobs for this query."
                        ),
                        "_reason": None if normalized else "no_results"
                    }
                    metrics.record_provider_call("adzuna", latency, bool(normalized))
                    if result["status"] == "success":
                        cache_set("adzuna", city, cache_key, result)
                    return result

                metrics.record_provider_call("adzuna", latency, False)
                return {
                    "status": "error",
                    "jobs": [],
                    "explanation": f"Adzuna API returned HTTP {res.status_code}.",
                    "_reason": "http_error"
                }

        except httpx.TimeoutException:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("adzuna", latency, False)
            return {"status": "error", "jobs": [], "explanation": "Adzuna API timed out.", "_reason": "api_timeout"}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            metrics.record_provider_call("adzuna", latency, False)
            return {"status": "error", "jobs": [], "explanation": f"Adzuna request failed: {e}", "_reason": "http_error"}
