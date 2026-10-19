"""Push notifications: device registry, preferences, senders (mocked),
safety-alert and event-reminder jobs, routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.core import kv
from apps.api.core.config import settings
from apps.api.services import accounts, push, push_jobs, user_data
from apps.api.services.push import PushError

SECRET = "test-internal-secret-0123456789abcdef"
TOKEN_A = "fcm-token-aaaaaaaaaaaaaaaaaaaa"
TOKEN_I = "a" * 64


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    kv.local_counters._data.clear()
    from apps.api.services.cache import ttl_cache
    ttl_cache.cache._cache.clear()
    with patch.object(settings, "ACCOUNTS_DB_PATH", str(tmp_path / "a.db")), \
         patch.object(settings, "AUTH_INTERNAL_SECRET", SECRET), \
         patch.object(settings, "REDIS_URL", None):
        yield


async def _user(email="p@example.com"):
    return await accounts.register(email, "password-123")


# ── registry + prefs ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_moves_token_and_validates():
    a, b = await _user("a@example.com"), await _user("b@example.com")
    await push.register(a.id, TOKEN_A, "android")
    await push.register(b.id, TOKEN_A, "android")          # same phone, new account
    assert await push.devices(a.id) == [] and len(await push.devices(b.id)) == 1
    with pytest.raises(PushError):
        await push.register(b.id, TOKEN_A, "windows")
    with pytest.raises(PushError):
        await push.register(b.id, "short", "ios")
    with pytest.raises(PushError):
        await push.register("u_missing", TOKEN_I, "ios")


@pytest.mark.asyncio
async def test_prefs_default_on_and_filter_recipients():
    a, b = await _user("a@example.com"), await _user("b@example.com")
    await push.register(a.id, TOKEN_A, "android")
    await push.register(b.id, TOKEN_I, "ios")
    assert (await push.get_prefs(a.id))["safety_alerts"] is True
    prefs = await push.set_prefs(b.id, {"event_reminders": False})
    assert prefs == {"safety_alerts": True, "event_reminders": False, "devices": 1}
    assert set(await push.recipients("safety_alerts")) == {a.id, b.id}
    assert await push.recipients("event_reminders") == [a.id]
    with pytest.raises(PushError):
        await push.set_prefs(a.id, {"marketing": True})


@pytest.mark.asyncio
async def test_account_deletion_removes_devices():
    a = await _user()
    await push.register(a.id, TOKEN_A, "android")
    await push.set_prefs(a.id, {"safety_alerts": False})
    await accounts.delete(a.id)
    assert await push.devices(a.id) == [] and await push.recipients("event_reminders") == []


# ── sending ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_routes_by_platform_prunes_dead_and_respects_prefs():
    a = await _user()
    await push.register(a.id, TOKEN_A, "android")
    await push.register(a.id, TOKEN_I, "ios")
    with patch.object(push, "fcm_configured", return_value=True), \
         patch.object(push, "apns_configured", return_value=True), \
         patch.object(push, "_send_fcm", AsyncMock(return_value="sent")) as fcm, \
         patch.object(push, "_send_apns", AsyncMock(return_value="dead")) as apns:
        counts = await push.send_to_user(a.id, "Hi", "There", url="/care", kind="safety_alerts")
    assert counts == {"sent": 1, "failed": 0, "dead": 1, "skipped": 0}
    assert fcm.call_args.args[4] == {"url": "/care", "channel": "alerts"}
    assert apns.await_count == 1
    assert [d["platform"] for d in await push.devices(a.id)] == ["android"]   # dead iOS token removed

    await push.set_prefs(a.id, {"safety_alerts": False})
    with patch.object(push, "_send_fcm", AsyncMock(return_value="sent")) as fcm:
        counts = await push.send_to_user(a.id, "Hi", "There", kind="safety_alerts")
    fcm.assert_not_called() and None
    assert counts["sent"] == 0 and counts["skipped"] == 1


@pytest.mark.asyncio
async def test_unconfigured_platforms_are_skipped():
    a = await _user()
    await push.register(a.id, TOKEN_A, "android")
    with patch.object(settings, "FCM_PROJECT_ID", None):
        assert (await push.send_to_user(a.id, "t", "b"))["skipped"] == 1


def test_apns_jwt_is_es256_with_kid():
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    push._apns_token.update(value=None, iat=0)
    with patch.object(settings, "APNS_PRIVATE_KEY", pem), patch.object(settings, "APNS_KEY_ID", "KEY123"), \
         patch.object(settings, "APNS_TEAM_ID", "TEAM123"):
        token = push._apns_jwt()
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "ES256" and header["kid"] == "KEY123"
    assert jwt.decode(token, options={"verify_signature": False})["iss"] == "TEAM123"


# ── jobs ───────────────────────────────────────────────────────────────────

PROFILE = {"city": "Boston", "cityLocation": {"lat": 42.36, "lon": -71.06, "city": "Boston", "country_code": "US"}}


@pytest.mark.asyncio
async def test_safety_alert_job_sends_once_and_only_urgent():
    a = await _user()
    await push.register(a.id, TOKEN_A, "android")
    await user_data.put(a.id, {"profile": PROFILE})
    alerts = [{"title": "Winter Storm Warning", "severity": "severe", "starts": "x", "detail": "Heavy snow"},
              {"title": "M4.6 earthquake", "severity": "moderate", "starts": "y", "detail": "far"}]
    send = AsyncMock(return_value={"sent": 1, "failed": 0, "dead": 0, "skipped": 0})
    with patch.object(push_jobs, "alerts_near", AsyncMock(return_value=alerts)), \
         patch.object(push_jobs.push, "send_to_user", send):
        first = await push_jobs.run_safety_alerts()
        second = await push_jobs.run_safety_alerts()
    assert first["notified"] == 1 and second["notified"] == 0
    assert "Winter Storm Warning near Boston" in send.call_args.args[1]
    assert send.call_args.kwargs == {"url": "/care", "kind": "safety_alerts"}


def test_parse_start_uses_city_timezone_for_naive_times():
    aware = push_jobs.parse_start("2026-10-23T19:00:00", "America/New_York")
    assert aware.utcoffset() == timedelta(hours=-4)
    assert push_jobs.parse_start("2026-10-23T23:00:00Z", None).tzinfo is not None
    assert push_jobs.parse_start("not a date", None) is None


@pytest.mark.asyncio
async def test_event_reminders_within_24h_once():
    a = await _user()
    await push.register(a.id, TOKEN_A, "android")
    now = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)       # 8 PM the evening before, in Boston
    await user_data.put(a.id, {"profile": PROFILE, "saved": {"savedEvents": [
        {"kind": "event", "id": "tm_1", "title": "Celtics vs Knicks", "venue": "TD Garden",
         "startsAt": "2026-10-23T19:00:00", "savedAt": 1},
        {"kind": "event", "id": "tm_2", "title": "Next month", "startsAt": "2026-11-23T19:00:00", "savedAt": 1},
        {"kind": "event", "id": "tm_3", "title": "Already over", "startsAt": "2026-10-20T19:00:00", "savedAt": 1},
    ]}})
    send = AsyncMock(return_value={"sent": 1, "failed": 0, "dead": 0, "skipped": 0})
    with patch.object(push_jobs, "_timezone", AsyncMock(return_value="America/New_York")), \
         patch.object(push_jobs.push, "send_to_user", send):
        first = await push_jobs.run_event_reminders(now)
        again = await push_jobs.run_event_reminders(now)
    assert first["reminded"] == 1 and again["reminded"] == 0
    title, body = send.call_args.args[1], send.call_args.args[2]
    assert title == "Tomorrow at 7:00 PM: Celtics vs Knicks" and body.startswith("TD Garden")
    assert send.call_args.kwargs == {"url": "/events/tm_1", "kind": "event_reminders"}


# ── routes ─────────────────────────────────────────────────────────────────

def test_push_routes_guarded_and_roundtrip():
    from apps.api.main import app
    c = TestClient(app)
    h = {"X-Internal-Auth": SECRET}
    uid = c.post("/v2/auth/register", headers=h, json={"email": "r@example.com", "password": "password-1"}).json()["user"]["id"]
    assert c.put(f"/v2/push/users/{uid}/devices", json={"token": TOKEN_A, "platform": "android"}).status_code == 403
    r = c.put(f"/v2/push/users/{uid}/devices", headers=h, json={"token": TOKEN_A, "platform": "android"})
    assert r.status_code == 200 and r.json()["prefs"]["devices"] == 1
    assert c.put(f"/v2/push/users/{uid}/prefs", headers=h, json={"event_reminders": False}).json()["prefs"]["event_reminders"] is False
    assert c.request("DELETE", f"/v2/push/users/{uid}/devices", headers=h, json={"token": TOKEN_A}).status_code == 200
    assert c.get(f"/v2/push/users/{uid}/prefs", headers=h).json()["prefs"]["devices"] == 0
    assert c.post("/v2/push/jobs/nope", headers=h).status_code == 404
    with patch.dict(push_jobs.JOBS, {"safety_alerts": AsyncMock(return_value={"users": 0})}):
        assert c.post("/v2/push/jobs/safety_alerts", headers=h).json() == {"job": "safety_alerts", "stats": {"users": 0}}
    assert set(c.get("/v2/push/status", headers=h).json()) == {"android", "ios"}
