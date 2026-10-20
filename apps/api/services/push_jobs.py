"""
Scheduled push jobs (run every ~15 minutes from a cron / Kubernetes CronJob
via POST /v2/push/jobs/{job}, internal secret required):

  safety_alerts     severe alerts (extreme / red / severe / orange) near each
                    user's home city: weather warnings, disasters, strong
                    earthquakes. Each alert is sent once per user.
  event_reminders   events the user saved that start within the next 24
                    hours (in the city's local time). One reminder per event.

Deduplication uses core/kv counters, so it's shared across instances when
REDIS_URL is set.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.api.core import kv
from apps.api.core.logging import get_logger
from apps.api.services import push, user_data
from apps.api.services.cache.ttl_cache import cache
from apps.api.services.domain.alerts import alerts_near
from apps.api.services.domain.common import PlaceRef, get_json

logger = get_logger(__name__)

URGENT = ("extreme", "red", "severe", "orange")
_ALERT_DEDUPE_S = 3 * 24 * 3600
_EVENT_DEDUPE_S = 3 * 24 * 3600


def _home_place(profile: Any) -> Optional[PlaceRef]:
    p = profile if isinstance(profile, dict) else {}
    loc = p.get("cityLocation") if isinstance(p.get("cityLocation"), dict) else None
    if not loc:
        return None
    try:
        lat, lon = float(loc["lat"]), float(loc["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    city = loc.get("city") or loc.get("name") or p.get("city")
    return PlaceRef(lat, lon, city, loc.get("country"), loc.get("country_code"), loc.get("region"))


async def _first_time(key: str, window_s: int) -> bool:
    return await kv.incr(key, window_s) == 1


def _digest(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:20]


async def run_safety_alerts() -> Dict[str, int]:
    stats = {"users": 0, "notified": 0, "sent": 0}
    for user_id in await push.recipients("safety_alerts"):
        stats["users"] += 1
        place = _home_place((await user_data.get(user_id)).get("profile"))
        if not place:
            continue
        for alert in (await alerts_near(place)) or []:
            if alert.get("severity") not in URGENT:
                continue
            if not await _first_time(f"push:alert:{user_id}:{_digest(alert.get('title'), alert.get('starts'))}",
                                     _ALERT_DEDUPE_S):
                continue
            where = f" near {place.label}" if place.city else ""
            body = alert.get("instruction") or alert.get("detail") or "Open Navis for details and local emergency numbers."
            counts = await push.send_to_user(user_id, f"⚠️ {alert['title']}{where}", body,
                                             url="/care", kind="safety_alerts")
            stats["notified"] += 1
            stats["sent"] += counts["sent"]
    logger.info("push.job.safety_alerts", **stats)
    return stats


async def _timezone(place: PlaceRef) -> Optional[str]:
    key = f"push.tz:{place.lat:.2f}:{place.lon:.2f}"
    tz = await cache.get(key)
    if tz:
        return tz
    data = await get_json("https://api.open-meteo.com/v1/forecast",
                          params={"latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 1,
                                  "daily": "sunrise"})
    tz = (data or {}).get("timezone")
    if tz:
        await cache.set(key, tz, ttl=30 * 24 * 3600)
    return tz


def parse_start(starts_at: str, tz_name: Optional[str]) -> Optional[datetime]:
    """Event start as an aware datetime. Times without an offset are the
    venue's local time, taken here as the user's home-city timezone."""
    try:
        dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name)) if tz_name else dt.replace(tzinfo=timezone.utc)
        except ZoneInfoNotFoundError:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt


def reminder_text(title: str, start: datetime, now: datetime, venue: Optional[str]) -> tuple[str, str]:
    local_now = now.astimezone(start.tzinfo)
    clock = start.strftime("%I:%M %p").lstrip("0")
    day = "Today" if start.date() == local_now.date() else "Tomorrow" if start.date() == (local_now + timedelta(days=1)).date() else start.strftime("%a")
    head = f"{day} at {clock}"
    return f"{head}: {title}"[:120], (f"{venue} · " if venue else "") + "Tap for details and directions."


async def run_event_reminders(now: Optional[datetime] = None) -> Dict[str, int]:
    now = now or datetime.now(timezone.utc)
    stats = {"users": 0, "reminded": 0, "sent": 0}
    for user_id in await push.recipients("event_reminders"):
        stats["users"] += 1
        data = await user_data.get(user_id)
        saved = data.get("saved") if isinstance(data.get("saved"), dict) else {}
        events = [e for e in saved.get("savedEvents") or [] if isinstance(e, dict) and e.get("startsAt")]
        if not events:
            continue
        place = _home_place(data.get("profile"))
        tz_name = await _timezone(place) if place else None
        for event in events:
            # The venue's timezone when the app saved it, else the user's home city.
            start = parse_start(str(event["startsAt"]), str(event.get("timezone") or "") or tz_name)
            if not start or not (now < start <= now + timedelta(hours=24)):
                continue
            if not await _first_time(f"push:event:{user_id}:{_digest(event.get('id'), event['startsAt'])}",
                                     _EVENT_DEDUPE_S):
                continue
            title, body = reminder_text(str(event.get("title") or "Your saved event"), start, now, event.get("venue"))
            event_id = str(event.get("id") or "")
            url = f"/events/{event_id}" if event_id and "/" not in event_id else "/saved"
            counts = await push.send_to_user(user_id, title, body, url=url, kind="event_reminders")
            stats["reminded"] += 1
            stats["sent"] += counts["sent"]
    logger.info("push.job.event_reminders", **stats)
    return stats


JOBS = {"safety_alerts": run_safety_alerts, "event_reminders": run_event_reminders}
