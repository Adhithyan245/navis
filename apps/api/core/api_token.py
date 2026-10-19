"""
Short-lived API tokens for signed-in users.

The Next server (which owns sessions) mints `v1.<user_id>.<expires>.<sig>`
and the browser / mobile app sends it as `Authorization: Bearer ...` on
costly routes (AI, voice, place lookups). The signature is HMAC-SHA256 with
API_TOKEN_SECRET, or a key derived from AUTH_INTERNAL_SECRET, so the
internal secret itself never leaves the servers.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Optional

from apps.api.core.config import settings

_UID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_LIFETIME_S = 60 * 60


def _key() -> Optional[bytes]:
    if settings.API_TOKEN_SECRET:
        return settings.API_TOKEN_SECRET.encode()
    if settings.AUTH_INTERNAL_SECRET:
        return hmac.new(settings.AUTH_INTERNAL_SECRET.encode(), b"navis-api-token-v1", hashlib.sha256).digest()
    return None


def sign(user_id: str, expires_at: int) -> str:
    key = _key()
    if key is None or not _UID.match(user_id):
        raise ValueError("cannot sign")
    body = f"v1.{user_id}.{int(expires_at)}"
    return f"{body}.{hmac.new(key, body.encode(), hashlib.sha256).hexdigest()}"


def verify(token: Optional[str]) -> Optional[str]:
    """The user id for a valid, unexpired token; otherwise None."""
    key = _key()
    if not key or not token or len(token) > 256:
        return None
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1" or not _UID.match(parts[1]):
        return None
    try:
        exp = int(parts[2])
    except ValueError:
        return None
    now = time.time()
    if exp < now or exp > now + MAX_LIFETIME_S + 60:
        return None
    expected = hmac.new(key, f"v1.{parts[1]}.{exp}".encode(), hashlib.sha256).hexdigest()
    return parts[1] if hmac.compare_digest(expected, parts[3]) else None


def from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return verify(authorization[7:].strip())
