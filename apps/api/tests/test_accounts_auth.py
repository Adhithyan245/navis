"""Accounts store + /v2/auth/* routes (temp DB, no network)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.api.services import accounts
from apps.api.services.accounts import AccountError

SECRET = "test-internal-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    with patch.object(accounts.settings, "ACCOUNTS_DB_PATH", str(tmp_path / "accounts.db")), \
         patch.object(accounts.settings, "AUTH_INTERNAL_SECRET", SECRET):
        from apps.api.core import kv
        kv.local_counters._data.clear()
        yield


@pytest.mark.asyncio
async def test_register_then_login():
    acct = await accounts.register("New.User@Example.com", "correct horse 9", "Ada")
    assert acct.email == "new.user@example.com"
    assert acct.providers == ["password"]
    again = await accounts.login("new.user@example.com", "correct horse 9")
    assert again.id == acct.id


@pytest.mark.asyncio
async def test_password_is_hashed_not_stored():
    await accounts.register("a@example.com", "s3cret-pass", None)
    with accounts._connect() as conn:
        stored = conn.execute("SELECT password_hash FROM accounts").fetchone()[0]
    assert "s3cret-pass" not in stored and stored.startswith("scrypt$")


@pytest.mark.asyncio
@pytest.mark.parametrize("email,password,code", [
    ("not-an-email", "longenough1", "invalid_email"),
    ("b@example.com", "short", "weak_password"),
    ("b@example.com", "12345678", "weak_password"),
])
async def test_register_validation(email, password, code):
    with pytest.raises(AccountError) as exc:
        await accounts.register(email, password)
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_duplicate_email_rejected():
    await accounts.register("dup@example.com", "password-1")
    with pytest.raises(AccountError) as exc:
        await accounts.register("DUP@example.com", "password-2")
    assert exc.value.code == "email_taken"


@pytest.mark.asyncio
async def test_wrong_password_and_lockout():
    await accounts.register("lock@example.com", "right-password")
    for _ in range(accounts._MAX_FAILS):
        with pytest.raises(AccountError) as exc:
            await accounts.login("lock@example.com", "wrong")
        assert exc.value.code == "bad_credentials"
    with pytest.raises(AccountError) as exc:
        await accounts.login("lock@example.com", "right-password")
    assert exc.value.code == "locked"


@pytest.mark.asyncio
async def test_unknown_email_is_bad_credentials_not_a_leak():
    with pytest.raises(AccountError) as exc:
        await accounts.login("nobody@example.com", "whatever1")
    assert exc.value.code == "bad_credentials"


@pytest.mark.asyncio
async def test_google_creates_then_reuses_account():
    a = await accounts.upsert_google("sub-1", "g@example.com", True, "G User", "http://pic")
    b = await accounts.upsert_google("sub-1", "g@example.com", True, None, None)
    assert a.id == b.id and a.providers == ["google"] and b.picture == "http://pic"


@pytest.mark.asyncio
async def test_google_links_verified_email_only():
    pw = await accounts.register("link@example.com", "password-1")
    with pytest.raises(AccountError) as exc:
        await accounts.upsert_google("sub-x", "link@example.com", False)
    assert exc.value.code == "unverified_email"
    linked = await accounts.upsert_google("sub-y", "link@example.com", True)
    assert linked.id == pw.id and set(linked.providers) == {"password", "google"}


# ── routes ─────────────────────────────────────────────────────────────────

def _client():
    from apps.api.main import app
    return TestClient(app)


def test_routes_require_internal_secret():
    c = _client()
    r = c.post("/v2/auth/register", json={"email": "x@example.com", "password": "password-1"})
    assert r.status_code == 403
    r = c.post("/v2/auth/login", headers={"X-Internal-Auth": "wrong"},
               json={"email": "x@example.com", "password": "password-1"})
    assert r.status_code == 403


def test_register_login_roundtrip_via_routes():
    c = _client()
    h = {"X-Internal-Auth": SECRET}
    r = c.post("/v2/auth/register", headers=h, json={"email": "r@example.com", "password": "password-1", "name": "R"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "r@example.com"
    user = r.json()["user"]
    assert set(user) == {"id", "email", "name", "picture", "providers", "session_version"}
    assert "scrypt$" not in str(user)
    r = c.post("/v2/auth/login", headers=h, json={"email": "r@example.com", "password": "nope-nope"})
    assert r.status_code == 401 and r.json()["detail"] == "That email and password don't match."
    r = c.post("/v2/auth/register", headers=h, json={"email": "r@example.com", "password": "password-2"})
    assert r.status_code == 409


def test_auth_routes_are_not_ip_rate_limited():
    from apps.api.core.security import is_rate_limit_exempt
    assert is_rate_limit_exempt("/v2/auth/login")


# ── per-account data sync ──────────────────────────────────────────────────

def _two_users(c):
    h = {"X-Internal-Auth": SECRET}
    a = c.post("/v2/auth/register", headers=h, json={"email": "a1@example.com", "password": "password-1"}).json()["user"]
    b = c.post("/v2/auth/register", headers=h, json={"email": "b1@example.com", "password": "password-1"}).json()["user"]
    return h, a["id"], b["id"]


def test_user_data_roundtrip_and_isolation():
    c = _client()
    h, a, b = _two_users(c)
    profile = {"city": "Reykjavik", "moveStage": "pre_arrival", "interests": ["food"]}
    r = c.put(f"/v2/auth/users/{a}/data", headers=h, json={"profile": profile, "checklist": {"items": {}}})
    assert r.status_code == 200
    got = c.get(f"/v2/auth/users/{a}/data", headers=h).json()["data"]
    assert got["profile"] == profile and got["checklist"] == {"items": {}} and got["saved"] is None
    assert set(got["updated_at"]) == {"profile", "checklist"}
    # The other account sees nothing of A's.
    other = c.get(f"/v2/auth/users/{b}/data", headers=h).json()["data"]
    assert other["profile"] is None and other["checklist"] is None


def test_user_data_sections_are_independent_and_null_deletes():
    c = _client()
    h, a, _ = _two_users(c)
    c.put(f"/v2/auth/users/{a}/data", headers=h, json={"profile": {"city": "X"}, "saved": {"savedPlaces": []}})
    c.put(f"/v2/auth/users/{a}/data", headers=h, json={"saved": {"savedPlaces": [{"id": "p"}]}})
    got = c.get(f"/v2/auth/users/{a}/data", headers=h).json()["data"]
    assert got["profile"] == {"city": "X"} and got["saved"]["savedPlaces"] == [{"id": "p"}]
    c.put(f"/v2/auth/users/{a}/data", headers=h, json={"profile": None})
    assert c.get(f"/v2/auth/users/{a}/data", headers=h).json()["data"]["profile"] is None


def test_user_data_guards():
    c = _client()
    h, a, _ = _two_users(c)
    assert c.get(f"/v2/auth/users/{a}/data").status_code == 403
    assert c.put(f"/v2/auth/users/{a}/data", headers={"X-Internal-Auth": "nope"}, json={"profile": {}}).status_code == 403
    assert c.put("/v2/auth/users/u_missing/data", headers=h, json={"profile": {"a": 1}}).status_code == 404
    assert c.put(f"/v2/auth/users/{a}/data", headers=h, json={"unknown": 1}).status_code == 422
    big = {"blob": "x" * (300 * 1024)}
    assert c.put(f"/v2/auth/users/{a}/data", headers=h, json={"saved": big}).status_code == 413


def test_user_data_payload_limit_allows_sync_bodies():
    from apps.api.core.security import MAX_PAYLOAD_BYTES, payload_limit_for
    assert payload_limit_for("/v2/auth/users/u_1/data") > MAX_PAYLOAD_BYTES
    assert payload_limit_for("/v2/auth/login") == MAX_PAYLOAD_BYTES
