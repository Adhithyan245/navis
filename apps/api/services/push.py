"""
services/push.py — push notifications to the Navis Android and iOS apps.

  Device registry   one row per device token (a token moves to whoever signs
                    in on that device), pruned when the push service says
                    the token is dead
  Preferences       per account: safety alerts, event reminders (both on by
                    default once the user allows notifications on a device)
  Senders           Android via Firebase Cloud Messaging HTTP v1 (service
                    account → OAuth token); iOS via APNs token auth (.p8
                    key → ES256 JWT) over HTTP/2

Nothing is sent when the matching credentials aren't configured; callers
get a per-platform count so ops can see what happened.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from apps.api.core.config import settings
from apps.api.core.http import get_session
from apps.api.core.logging import get_logger
from apps.api.services import db

logger = get_logger(__name__)

PLATFORMS = ("android", "ios")
KINDS = ("safety_alerts", "event_reminders")
MAX_DEVICES_PER_USER = 10


class PushError(Exception):
    """`code`: bad_platform | bad_token | bad_pref | no_account."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ── registry + preferences (sync; run on a worker thread) ──────────────────

def _register(user_id: str, token: str, platform: str) -> None:
    if platform not in PLATFORMS:
        raise PushError("bad_platform")
    token = (token or "").strip()
    if not (16 <= len(token) <= 4096) or any(c.isspace() for c in token):
        raise PushError("bad_token")
    now = time.time()
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM accounts WHERE id = ?", (user_id,)).fetchone():
            raise PushError("no_account")
        conn.execute(
            "INSERT INTO push_devices (token, user_id, platform, created_at, last_seen) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(token) DO UPDATE SET user_id = excluded.user_id, platform = excluded.platform, "
            "last_seen = excluded.last_seen",
            (token, user_id, platform, now, now),
        )
        rows = conn.execute(
            "SELECT token FROM push_devices WHERE user_id = ? ORDER BY last_seen DESC", (user_id,)
        ).fetchall()
        for row in rows[MAX_DEVICES_PER_USER:]:
            conn.execute("DELETE FROM push_devices WHERE token = ?", (row["token"],))


def _unregister(user_id: str, token: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM push_devices WHERE token = ? AND user_id = ?", (token, user_id))


def _forget_token(token: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM push_devices WHERE token = ?", (token,))


def _devices(user_id: str) -> List[Dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT token, platform FROM push_devices WHERE user_id = ?", (user_id,)).fetchall()
    return [{"token": r["token"], "platform": r["platform"]} for r in rows]


def _get_prefs(user_id: str) -> Dict[str, bool]:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM push_prefs WHERE user_id = ?", (user_id,)).fetchone()
        devices = conn.execute("SELECT COUNT(*) AS n FROM push_devices WHERE user_id = ?", (user_id,)).fetchone()
    prefs = {k: bool(row[k]) if row else True for k in KINDS}
    return {**prefs, "devices": int(devices["n"] if devices else 0)}


def _set_prefs(user_id: str, changes: Dict[str, Any]) -> Dict[str, bool]:
    if not changes or any(k not in KINDS or not isinstance(v, bool) for k, v in changes.items()):
        raise PushError("bad_pref")
    current = _get_prefs(user_id)
    merged = {k: changes.get(k, current[k]) for k in KINDS}
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM accounts WHERE id = ?", (user_id,)).fetchone():
            raise PushError("no_account")
        conn.execute(
            "INSERT INTO push_prefs (user_id, safety_alerts, event_reminders, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET safety_alerts = excluded.safety_alerts, "
            "event_reminders = excluded.event_reminders, updated_at = excluded.updated_at",
            (user_id, int(merged["safety_alerts"]), int(merged["event_reminders"]), time.time()),
        )
    return _get_prefs(user_id)


def _recipients(kind: str) -> List[str]:
    """Accounts with at least one device and this kind of notification on."""
    if kind not in KINDS:
        raise PushError("bad_pref")
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT d.user_id AS user_id FROM push_devices d "
            f"LEFT JOIN push_prefs p ON p.user_id = d.user_id "
            f"WHERE p.user_id IS NULL OR p.{kind} = 1"
        ).fetchall()
    return [r["user_id"] for r in rows]


async def register(user_id: str, token: str, platform: str) -> None:
    await asyncio.to_thread(_register, user_id, token, platform)


async def unregister(user_id: str, token: str) -> None:
    await asyncio.to_thread(_unregister, user_id, token)


async def devices(user_id: str) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_devices, user_id)


async def get_prefs(user_id: str) -> Dict[str, bool]:
    return await asyncio.to_thread(_get_prefs, user_id)


async def set_prefs(user_id: str, changes: Dict[str, Any]) -> Dict[str, bool]:
    return await asyncio.to_thread(_set_prefs, user_id, changes)


async def recipients(kind: str) -> List[str]:
    return await asyncio.to_thread(_recipients, kind)


# ── credentials ────────────────────────────────────────────────────────────

def fcm_configured() -> bool:
    return bool(settings.FCM_PROJECT_ID and settings.FCM_SERVICE_ACCOUNT_JSON)


def apns_configured() -> bool:
    return bool(settings.APNS_KEY_ID and settings.APNS_TEAM_ID and settings.APNS_PRIVATE_KEY and settings.APNS_BUNDLE_ID)


def _service_account() -> Dict[str, Any]:
    raw = (settings.FCM_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw.startswith("{"):
        raw = Path(raw).read_text(encoding="utf-8")
    return json.loads(raw)


_fcm_token: Dict[str, Any] = {"value": None, "exp": 0.0}
_apns_token: Dict[str, Any] = {"value": None, "iat": 0.0}


async def _fcm_access_token(session: aiohttp.ClientSession) -> Optional[str]:
    if _fcm_token["value"] and _fcm_token["exp"] - 120 > time.time():
        return _fcm_token["value"]
    import jwt  # PyJWT; imported lazily so the API runs without push configured

    sa = _service_account()
    now = int(time.time())
    assertion = jwt.encode(
        {"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/firebase.messaging",
         "aud": sa.get("token_uri", "https://oauth2.googleapis.com/token"), "iat": now, "exp": now + 3600},
        sa["private_key"], algorithm="RS256",
    )
    async with session.post(sa.get("token_uri", "https://oauth2.googleapis.com/token"),
                            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
                            timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200 or not data.get("access_token"):
            logger.warning("push.fcm.auth_failed", status=resp.status)
            return None
    _fcm_token.update(value=data["access_token"], exp=now + int(data.get("expires_in", 3600)))
    return _fcm_token["value"]


def _apns_jwt() -> str:
    # APNs accepts a provider token for up to an hour; refresh at 50 minutes.
    if _apns_token["value"] and time.time() - _apns_token["iat"] < 50 * 60:
        return _apns_token["value"]
    import jwt

    now = int(time.time())
    key = settings.APNS_PRIVATE_KEY.replace("\\n", "\n")
    token = jwt.encode({"iss": settings.APNS_TEAM_ID, "iat": now}, key, algorithm="ES256",
                       headers={"kid": settings.APNS_KEY_ID})
    _apns_token.update(value=token, iat=now)
    return token


# ── senders ────────────────────────────────────────────────────────────────

async def _send_fcm(session: aiohttp.ClientSession, token: str, title: str, body: str,
                    data: Dict[str, str]) -> str:
    """'sent' | 'dead' (token invalid) | 'failed'."""
    access = await _fcm_access_token(session)
    if not access:
        return "failed"
    message = {"message": {
        "token": token,
        "notification": {"title": title, "body": body},
        "data": data,
        "android": {"priority": "high", "notification": {"channel_id": data.get("channel", "general")}},
    }}
    url = f"https://fcm.googleapis.com/v1/projects/{settings.FCM_PROJECT_ID}/messages:send"
    try:
        async with session.post(url, json=message, headers={"Authorization": f"Bearer {access}"},
                                timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return "sent"
            detail = await resp.text()
            if resp.status == 404 or "UNREGISTERED" in detail or (resp.status == 400 and "INVALID_ARGUMENT" in detail
                                                                     and "token" in detail.lower()):
                return "dead"
            logger.info("push.fcm.failed", status=resp.status)
            return "failed"
    except Exception as exc:  # noqa: BLE001
        logger.info("push.fcm.error", error=type(exc).__name__)
        return "failed"


_apns_client = None


def _apns() -> Any:
    global _apns_client
    if _apns_client is None:
        import httpx  # HTTP/2 (APNs requires it; aiohttp is HTTP/1.1 only)

        _apns_client = httpx.AsyncClient(http2=True, timeout=10.0)
    return _apns_client


async def _send_apns(token: str, title: str, body: str, data: Dict[str, str]) -> str:
    host = "api.sandbox.push.apple.com" if settings.APNS_USE_SANDBOX else "api.push.apple.com"
    payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default",
                       "interruption-level": "time-sensitive" if data.get("channel") == "alerts" else "active"},
               **data}
    try:
        resp = await _apns().post(
            f"https://{host}/3/device/{token}", json=payload,
            headers={"authorization": f"bearer {_apns_jwt()}", "apns-topic": settings.APNS_BUNDLE_ID,
                     "apns-push-type": "alert", "apns-priority": "10"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("push.apns.error", error=type(exc).__name__)
        return "failed"
    if resp.status_code == 200:
        return "sent"
    reason = ""
    try:
        reason = resp.json().get("reason", "")
    except ValueError:
        pass
    if resp.status_code == 410 or reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
        return "dead"
    logger.info("push.apns.failed", status=resp.status_code, reason=reason)
    return "failed"


async def send_to_user(user_id: str, title: str, body: str, *, url: Optional[str] = None,
                       kind: Optional[str] = None) -> Dict[str, int]:
    """Send to every device of the account (respecting the preference for
    `kind`, if given). Dead tokens are removed. Returns counts."""
    counts = {"sent": 0, "failed": 0, "dead": 0, "skipped": 0}
    if kind is not None:
        prefs = await get_prefs(user_id)
        if not prefs.get(kind, False):
            counts["skipped"] = prefs.get("devices", 0)
            return counts
    data = {"url": url or "/today", "channel": "alerts" if kind == "safety_alerts" else "general"}
    title, body = title[:120], body[:400]
    session = get_session()
    for device in await devices(user_id):
        if device["platform"] == "android":
            if not fcm_configured():
                counts["skipped"] += 1
                continue
            outcome = await _send_fcm(session, device["token"], title, body, data)
        else:
            if not apns_configured():
                counts["skipped"] += 1
                continue
            outcome = await _send_apns(device["token"], title, body, data)
        counts[outcome] += 1
        if outcome == "dead":
            await asyncio.to_thread(_forget_token, device["token"])
    return counts
