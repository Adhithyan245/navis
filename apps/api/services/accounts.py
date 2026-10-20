"""
Accounts — user records for sign-in (email + password, Google, Apple).

Stored via services/db.py: Postgres when ACCOUNTS_DATABASE_URL is set,
otherwise a local SQLite file. Calls run on a worker thread.

Passwords are hashed with scrypt (stdlib) and a per-user random salt;
verification is constant-time. Google and Apple accounts are keyed by the
provider's stable `sub`, and linked to an existing email account only when
the provider reports the email as verified.

Failed-login and sign-up throttles (per email and per client IP) live in
core/kv.py, so they're shared across workers when Redis is configured.

Sessions are NOT handled here: the Next.js server signs its own session
cookie after one of these calls succeeds. `session_version` lets a user
sign out everywhere (the Next server rejects cookies with an older one).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from apps.api.core import kv
from apps.api.core.config import settings
from apps.api.services import db

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
MIN_PASSWORD_LEN = 8

# scrypt parameters (~16 MB, a few tens of ms per hash).
_N, _R, _P = 2**14, 8, 1

# Throttles.
_MAX_FAILS = 5                 # wrong passwords per email per window
_FAIL_WINDOW_S = 15 * 60
_MAX_IP_FAILS = 30             # wrong passwords per client IP per window
_MAX_SIGNUPS_PER_IP = 10       # new accounts per client IP per hour


class AccountError(Exception):
    """`code` is one of: invalid_email, weak_password, email_taken,
    bad_credentials, locked, unverified_email, rate_limited."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Account:
    id: str
    email: str
    name: Optional[str]
    picture: Optional[str]
    providers: list
    session_version: int = 0

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "name": self.name,
                "picture": self.picture, "providers": self.providers,
                "session_version": self.session_version}


# Kept for callers/tests that open the accounts DB directly.
_connect = db.connect


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        # Burn comparable time so "no such user" isn't distinguishable.
        hashlib.scrypt(password.encode(), salt=b"0" * 16, n=_N, r=_R, p=_P, dklen=32)
        return False
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p), dklen=len(digest_hex) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def _row_to_account(row) -> Account:
    keys = row.keys()
    providers = []
    if row["password_hash"]:
        providers.append("password")
    if row["google_sub"]:
        providers.append("google")
    if "apple_sub" in keys and row["apple_sub"]:
        providers.append("apple")
    version = row["session_version"] if "session_version" in keys else 0
    return Account(id=row["id"], email=row["email"], name=row["name"],
                   picture=row["picture"], providers=providers, session_version=int(version or 0))


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _email_key(email: str) -> str:
    return "login:email:" + hashlib.sha256(email.encode()).hexdigest()[:32]


# ── sync implementations (run on a worker thread) ──────────────────────────

def _register(email: str, password: str, name: Optional[str]) -> Account:
    email = normalize_email(email)
    if not _EMAIL.match(email):
        raise AccountError("invalid_email")
    if len(password or "") < MIN_PASSWORD_LEN or password.strip() != password or password.isdigit():
        raise AccountError("weak_password")
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
        if existing:
            raise AccountError("email_taken")
        acct_id = "u_" + secrets.token_hex(12)
        now = time.time()
        conn.execute(
            "INSERT INTO accounts (id, email, name, password_hash, created_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (acct_id, email, (name or "").strip()[:80] or None, _hash_password(password), now, now),
        )
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
    return _row_to_account(row)


def _login(email: str, password: str) -> Account:
    email = normalize_email(email)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
        ok = _verify_password(password or "", row["password_hash"] if row else None)
        if not ok:
            raise AccountError("bad_credentials")
        conn.execute("UPDATE accounts SET last_login_at = ? WHERE id = ?", (time.time(), row["id"]))
    return _row_to_account(row)


_OAUTH_COLUMNS = {"google": "google_sub", "apple": "apple_sub"}


def _oauth(provider: str, subject: str, email: str, email_verified: bool,
           name: Optional[str], picture: Optional[str]) -> Account:
    col = _OAUTH_COLUMNS[provider]
    email = normalize_email(email)
    if not subject or not _EMAIL.match(email):
        raise AccountError("invalid_email")
    with _connect() as conn:
        row = conn.execute(f"SELECT * FROM accounts WHERE {col} = ?", (subject,)).fetchone()
        now = time.time()
        if row is None:
            by_email = conn.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
            if by_email is not None:
                # Linking to an existing account: only when the provider
                # vouches for the address, or anyone could claim it.
                if not email_verified:
                    raise AccountError("unverified_email")
                conn.execute(
                    f"UPDATE accounts SET {col} = ?, name = COALESCE(name, ?), "
                    "picture = COALESCE(?, picture), last_login_at = ? WHERE id = ?",
                    (subject, name, picture, now, by_email["id"]),
                )
                acct_id = by_email["id"]
            else:
                acct_id = "u_" + secrets.token_hex(12)
                conn.execute(
                    f"INSERT INTO accounts (id, email, name, picture, {col}, created_at, last_login_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (acct_id, email, (name or "")[:80] or None, picture, subject, now, now),
                )
        else:
            acct_id = row["id"]
            conn.execute(
                "UPDATE accounts SET picture = COALESCE(?, picture), name = COALESCE(name, ?), "
                "last_login_at = ? WHERE id = ?",
                (picture, name, now, acct_id),
            )
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
    return _row_to_account(row)


def _delete(acct_id: str) -> bool:
    with _connect() as conn:
        conn.execute("DELETE FROM user_data WHERE user_id = ?", (acct_id,))
        conn.execute("DELETE FROM push_devices WHERE user_id = ?", (acct_id,))
        conn.execute("DELETE FROM push_prefs WHERE user_id = ?", (acct_id,))
        cur = conn.execute("DELETE FROM accounts WHERE id = ?", (acct_id,))
        return (cur.rowcount or 0) > 0


def _bump_sessions(acct_id: str) -> Optional[Account]:
    with _connect() as conn:
        conn.execute("UPDATE accounts SET session_version = session_version + 1 WHERE id = ?", (acct_id,))
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
    return _row_to_account(row) if row else None


def _export(acct_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
    if not row:
        return None
    acct = _row_to_account(row)
    return {**acct.public(), "created_at": row["created_at"], "last_login_at": row["last_login_at"]}


def _get(acct_id: str) -> Optional[Account]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
    return _row_to_account(row) if row else None


# ── async API ──────────────────────────────────────────────────────────────

async def register(email: str, password: str, name: Optional[str] = None,
                   client_ip: Optional[str] = None) -> Account:
    if client_ip and not await kv.allow(f"signup:ip:{client_ip}", _MAX_SIGNUPS_PER_IP, 3600):
        raise AccountError("rate_limited")
    return await asyncio.to_thread(_register, email, password, name)


async def login(email: str, password: str, client_ip: Optional[str] = None) -> Account:
    email_key = _email_key(normalize_email(email))
    if await kv.peek(email_key, _FAIL_WINDOW_S) >= _MAX_FAILS:
        raise AccountError("locked")
    if client_ip and await kv.peek(f"login:ip:{client_ip}", _FAIL_WINDOW_S) >= _MAX_IP_FAILS:
        raise AccountError("rate_limited")
    try:
        acct = await asyncio.to_thread(_login, email, password)
    except AccountError:
        await kv.incr(email_key, _FAIL_WINDOW_S)
        if client_ip:
            await kv.incr(f"login:ip:{client_ip}", _FAIL_WINDOW_S)
        raise
    await kv.reset(email_key, _FAIL_WINDOW_S)
    return acct


async def upsert_google(subject: str, email: str, email_verified: bool,
                        name: Optional[str] = None, picture: Optional[str] = None) -> Account:
    return await asyncio.to_thread(_oauth, "google", subject, email, email_verified, name, picture)


async def upsert_apple(subject: str, email: str, email_verified: bool,
                       name: Optional[str] = None) -> Account:
    return await asyncio.to_thread(_oauth, "apple", subject, email, email_verified, name, None)


async def get(acct_id: str) -> Optional[Account]:
    return await asyncio.to_thread(_get, acct_id)


async def delete(acct_id: str) -> bool:
    """Permanently delete the account and everything synced to it."""
    return await asyncio.to_thread(_delete, acct_id)


async def sign_out_everywhere(acct_id: str) -> Optional[Account]:
    return await asyncio.to_thread(_bump_sessions, acct_id)


async def export(acct_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_export, acct_id)


async def ping() -> bool:
    return await asyncio.to_thread(db.ping)


def internal_secret_ok(provided: Optional[str]) -> bool:
    expected = settings.AUTH_INTERNAL_SECRET or (os.environ.get("AUTH_INTERNAL_SECRET") or "").strip().strip("'\"").strip()
    provided = (provided or "").strip()
    return bool(expected) and bool(provided) and hmac.compare_digest(provided.encode(), expected.encode())
