"""Security layer + scale-out pieces: API tokens, rate limits, payload caps,
security headers, ops guard, readiness, SSRF guard, account lifecycle."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.core import api_token, kv, netguard, security
from apps.api.core.config import settings
from apps.api.services import accounts
from apps.api.services.accounts import AccountError

SECRET = "test-internal-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    kv.local_counters._data.clear()
    with patch.object(settings, "ACCOUNTS_DB_PATH", str(tmp_path / "a.db")), \
         patch.object(settings, "AUTH_INTERNAL_SECRET", SECRET), \
         patch.object(settings, "REDIS_URL", None):
        yield
    kv.local_counters._data.clear()


def _client():
    from apps.api.main import app
    return TestClient(app)


# ── API tokens ─────────────────────────────────────────────────────────────

def test_token_roundtrip_and_tamper():
    tok = api_token.sign("u_abc", int(time.time()) + 600)
    assert api_token.verify(tok) == "u_abc"
    assert api_token.from_header(f"Bearer {tok}") == "u_abc"
    assert api_token.verify(tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None
    assert api_token.verify(tok.replace("u_abc", "u_xyz")) is None
    assert api_token.verify(api_token.sign("u_abc", int(time.time()) - 1)) is None
    assert api_token.verify(api_token.sign("u_abc", int(time.time()) + 10 * 3600)) is None   # too long-lived


def test_costly_routes_need_token_when_required():
    c = _client()
    with patch.object(settings, "REQUIRE_API_TOKEN", True):
        assert c.post("/v2/query", json={"query": "x"}).status_code == 401
        assert c.get("/v2/maps/place", params={"lat": 1, "lon": 2}).status_code == 401
        assert c.get("/v2/maps/categories").status_code == 200          # cheap routes stay open
        assert c.get("/health").status_code == 200


def test_costly_limit_is_per_user():
    c = _client()
    tok = api_token.sign("u_one", int(time.time()) + 600)
    with patch.object(security, "COSTLY_PREFIXES", (("/v2/maps/place", 1),)), \
         patch("apps.api.routes.maps.place_details", return_value={"place": {}}) as _:
        h = {"Authorization": f"Bearer {tok}"}
        assert c.get("/v2/maps/place", params={"lat": 1, "lon": 2}, headers=h).status_code != 429
        assert c.get("/v2/maps/place", params={"lat": 1, "lon": 2}, headers=h).status_code == 429
        other = {"Authorization": f"Bearer {api_token.sign('u_two', int(time.time()) + 600)}"}
        assert c.get("/v2/maps/place", params={"lat": 1, "lon": 2}, headers=other).status_code != 429


# ── middleware ─────────────────────────────────────────────────────────────

def test_security_headers_present():
    r = _client().get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in r.headers           # dev
    with patch.object(settings, "ENV", "production"):
        assert "strict-transport-security" in _client().get("/health").headers


def test_chunked_body_over_limit_is_rejected():
    c = _client()

    def chunks():
        for _ in range(100):
            yield b"x" * 1024

    r = c.post("/v2/query", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_ops_endpoints_hidden_in_production():
    c = _client()
    with patch.object(settings, "ENV", "production"):
        assert c.get("/metrics").status_code == 404
        assert c.get("/providers/diagnostics").status_code == 404
        assert c.get("/metrics", headers={"X-Internal-Auth": SECRET}).status_code == 200
        assert c.get("/metrics", headers={"Authorization": f"Bearer {SECRET}"}).status_code == 200


def test_readiness_reports_db():
    r = _client().get("/ready")
    assert r.status_code == 200 and r.json()["checks"]["accounts_db"] is True


def test_mask_api_keys():
    assert "secret" not in security.mask_api_keys("https://x/y?apiKey=secret&q=1")


# ── kv / cache ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_counters_and_lru_cache():
    assert await kv.allow("t", 2, 60) and await kv.allow("t", 2, 60)
    assert not await kv.allow("t", 2, 60)
    await kv.reset("t", 60)
    assert await kv.peek("t", 60) == 0

    from apps.api.services.cache.ttl_cache import AsyncMemoryCache
    c = AsyncMemoryCache(max_entries=2)
    for k in "abc":
        await c.set(k, k, ttl=60)
    assert await c.get("a") is None and await c.get("c") == "c"


# ── SSRF guard ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost:8100/", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/", "ftp://example.com/", "http://user:pw@example.com/", "http://example.com:8080/",
    "http://[::1]/",
])
async def test_private_and_odd_urls_blocked(url):
    assert not await netguard.is_public_url(url)


# ── account lifecycle ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_account_removes_data():
    from apps.api.services import user_data
    acct = await accounts.register("del@example.com", "password-123")
    await user_data.put(acct.id, {"profile": {"city": "Boston"}})
    assert await accounts.delete(acct.id)
    assert await accounts.get(acct.id) is None
    assert (await user_data.get(acct.id))["profile"] is None
    with pytest.raises(AccountError):
        await accounts.login("del@example.com", "password-123")


@pytest.mark.asyncio
async def test_sign_out_everywhere_bumps_version():
    acct = await accounts.register("sv@example.com", "password-123")
    assert acct.session_version == 0
    assert (await accounts.sign_out_everywhere(acct.id)).session_version == 1


@pytest.mark.asyncio
async def test_apple_links_verified_email_only():
    pw = await accounts.register("apple@example.com", "password-123")
    with pytest.raises(AccountError):
        await accounts.upsert_apple("apple-sub-1", "apple@example.com", False)
    linked = await accounts.upsert_apple("apple-sub-1", "apple@example.com", True, "A")
    assert linked.id == pw.id and "apple" in linked.providers
    relay = await accounts.upsert_apple("apple-sub-2", "x1@privaterelay.appleid.com", True)
    assert relay.id != pw.id


@pytest.mark.asyncio
async def test_ip_throttles():
    for i in range(accounts._MAX_SIGNUPS_PER_IP):
        await accounts.register(f"ip{i}@example.com", "password-123", client_ip="9.9.9.9")
    with pytest.raises(AccountError) as exc:
        await accounts.register("ipx@example.com", "password-123", client_ip="9.9.9.9")
    assert exc.value.code == "rate_limited"
    for i in range(accounts._MAX_IP_FAILS):
        with pytest.raises(AccountError):
            await accounts.login(f"nobody{i}@example.com", "wrong-password", client_ip="8.8.8.8")
    with pytest.raises(AccountError) as exc:
        await accounts.login("ip0@example.com", "password-123", client_ip="8.8.8.8")
    assert exc.value.code == "rate_limited"


def test_delete_and_export_routes():
    c = _client()
    h = {"X-Internal-Auth": SECRET}
    uid = c.post("/v2/auth/register", headers=h, json={"email": "e@example.com", "password": "password-1"}).json()["user"]["id"]
    exp = c.get(f"/v2/auth/users/{uid}/export", headers=h).json()
    assert exp["account"]["email"] == "e@example.com" and "data" in exp
    assert c.delete(f"/v2/auth/users/{uid}").status_code == 403
    assert c.delete(f"/v2/auth/users/{uid}", headers=h).json() == {"deleted": True}
    assert c.get(f"/v2/auth/users/{uid}", headers=h).status_code == 404


# ── optional live backends (set TEST_POSTGRES_URL / TEST_REDIS_URL) ────────

import os  # noqa: E402


def test_pg_placeholder_translation():
    from apps.api.services.db import _PgConn

    class Fake:
        def execute(self, sql, params):
            return sql, params

    assert _PgConn(Fake()).execute("SELECT * FROM a WHERE x = ? AND y = ?", (1, 2)) == (
        "SELECT * FROM a WHERE x = %s AND y = %s", (1, 2))


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
async def test_accounts_on_postgres():
    from apps.api.services import db, user_data
    with patch.object(settings, "ACCOUNTS_DATABASE_URL", os.environ["TEST_POSTGRES_URL"]):
        db.reset_for_tests()
        email = f"pg{int(time.time() * 1000)}@example.com"
        acct = await accounts.register(email, "password-123")
        assert (await accounts.login(email, "password-123")).id == acct.id
        await user_data.put(acct.id, {"saved": [1, 2]})
        assert (await user_data.get(acct.id))["saved"] == [1, 2]
        assert await accounts.delete(acct.id)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("TEST_REDIS_URL"), reason="TEST_REDIS_URL not set")
async def test_counters_on_redis():
    with patch.object(settings, "REDIS_URL", os.environ["TEST_REDIS_URL"]):
        kv.redis_state._client = None
        key = f"t{time.time()}"
        assert await kv.redis_ping() is True
        assert await kv.incr(key, 60) == 1 and await kv.incr(key, 60) == 2
        await kv.redis_set("c:x", {"a": 1}, 60)
        assert await kv.redis_get("c:x") == (True, {"a": 1})
