"""
core/security.py

Security middleware for Navis. All of it is plain ASGI (not
BaseHTTPMiddleware) so it sees streamed request bodies and streamed
responses through to the end.

  - SecurityHeadersMiddleware  nosniff, frame-deny, referrer, HSTS (prod)
  - RateLimitMiddleware        per-user (API token) or per-IP limits, with a
                               tighter budget on AI / voice / lookup routes;
                               shared via Redis when REDIS_URL is set; also
                               requires an API token on costly routes when
                               api_token_required()
  - PayloadSizeMiddleware      counts body bytes as they arrive (chunked
                               uploads can't skip the cap)
  - StreamAbuseMiddleware      concurrent NDJSON streams per client, held
                               until the stream actually finishes
  - mask_api_keys              credential masking for log strings

Client IPs come from the ASGI scope; run uvicorn with --proxy-headers and
--forwarded-allow-ips set to the load balancer so that's the real client.
"""
from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from typing import Dict, Optional, Tuple

import orjson

from apps.api.core import api_token, kv
from apps.api.core.config import api_token_required, is_production
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_REQUESTS_PER_MINUTE = 120
MAX_PAYLOAD_BYTES       = 64_000       # 64 KB
# Audio uploads are legitimately large; matches the voice route's 25 MiB cap.
VOICE_PAYLOAD_BYTES     = 25 * 1024 * 1024
VOICE_PATHS             = ("/v2/voice",)
SLIDING_WINDOW_SECONDS  = 60
MAX_STREAMS_PER_IP      = 5            # concurrent NDJSON streams per client

# Costly routes: model calls, speech-to-text, third-party lookups with strict
# usage policies. Tighter per-client budget, and an API token in production.
COSTLY_PREFIXES: Tuple[Tuple[str, int], ...] = (
    ("/v2/query", 20),
    ("/v2/today", 10),
    ("/v2/voice", 15),
    ("/v2/workflow", 20),
    ("/interact", 20),
    ("/v2/care", 20),
    ("/v2/maps/place", 40),
)
STREAM_PREFIXES = ("/interact", "/v2/query", "/v2/workflow", "/v2/today")

# Liveness probes and the ops endpoints (guarded separately) aren't counted.
RATE_LIMIT_EXEMPT_PATHS    = ("/health", "/ready", "/metrics")
# /v2/auth/* and /v2/push/* are called only by the Next server / cron (one IP
# for every user, internal secret required); /v2/auth
# applies per-client-IP and per-email throttles itself (routes/auth.py).
RATE_LIMIT_EXEMPT_PREFIXES = ("/providers/", "/health/", "/v2/auth/", "/v2/push/")

# Account data sync sends profile + saved items + checklist in one request.
USER_DATA_PAYLOAD_BYTES = 1024 * 1024

# Regex for masking bearer tokens / API keys in log strings
_KEY_PATTERN = re.compile(
    r'(Authorization:\s*(?:Bearer\s+|))[A-Za-z0-9\-._~+/]+=*',
    re.IGNORECASE
)
_QUERY_KEY_PATTERN = re.compile(r'((?:api_?key|apikey|key|token|access_token|client_secret)=)[^&\s"\']+', re.IGNORECASE)


def mask_api_keys(text: str) -> str:
    """Replace credential values with *** in any string before logging."""
    return _QUERY_KEY_PATTERN.sub(r'\1***', _KEY_PATTERN.sub(r'\1***MASKED***', text))


def is_rate_limit_exempt(path: str) -> bool:
    return (
        path in RATE_LIMIT_EXEMPT_PATHS
        or path == "/providers"
        or path.startswith(RATE_LIMIT_EXEMPT_PREFIXES)
    )


def payload_limit_for(path: str) -> int:
    if path in VOICE_PATHS:
        return VOICE_PAYLOAD_BYTES
    if path.startswith("/v2/auth/users/") and path.endswith("/data"):
        return USER_DATA_PAYLOAD_BYTES
    return MAX_PAYLOAD_BYTES


def costly_limit(path: str) -> Optional[int]:
    for prefix, limit in COSTLY_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return limit
    return None


def _client_ip(scope) -> str:
    client = scope.get("client")
    return client[0] if client else "unknown"


def _header(scope, name: bytes) -> Optional[str]:
    for k, v in scope.get("headers") or []:
        if k == name:
            return v.decode("latin-1")
    return None


async def _send_json(send, status: int, body: dict, extra_headers=()) -> None:
    payload = orjson.dumps(body)
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode()),
                    *extra_headers],
    })
    await send({"type": "http.response.body", "body": payload})


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {k.lower() for k, _ in headers}
                for k, v in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"cross-origin-resource-policy", b"same-site"),
                    (b"permissions-policy", b"camera=(), geolocation=(), microphone=()"),
                ):
                    if k not in present:
                        headers.append((k, v))
                if is_production() and b"strict-transport-security" not in present:
                    headers.append((b"strict-transport-security", b"max-age=63072000; includeSubDomains"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if is_rate_limit_exempt(path):
            return await self.app(scope, receive, send)

        user_id = api_token.from_header(_header(scope, b"authorization"))
        costly = costly_limit(path)
        if costly is not None and user_id is None and api_token_required():
            return await _send_json(send, 401, {"error": "Please sign in to use this feature."})
        identity = f"u:{user_id}" if user_id else f"ip:{_client_ip(scope)}"
        scope.setdefault("state", {})["user_id"] = user_id

        if not await kv.allow(f"all:{identity}", MAX_REQUESTS_PER_MINUTE, SLIDING_WINDOW_SECONDS):
            logger.warning("rate_limit.exceeded", identity=identity[:40])
            return await _send_json(send, 429, {"error": "Rate limit exceeded. Try again later."},
                                    [(b"retry-after", str(SLIDING_WINDOW_SECONDS).encode())])
        if costly is not None and not await kv.allow(f"costly:{identity}:{path.split('/')[2] if path.count('/') > 1 else path}",
                                                     costly, SLIDING_WINDOW_SECONDS):
            logger.warning("rate_limit.costly_exceeded", identity=identity[:40], path=path)
            return await _send_json(send, 429, {"error": "You're going a bit fast. Try again in a minute."},
                                    [(b"retry-after", str(SLIDING_WINDOW_SECONDS).encode())])
        return await self.app(scope, receive, send)


class PayloadSizeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = payload_limit_for(scope.get("path", ""))
        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                return await _send_json(send, 400, {"error": "Invalid Content-Length."})
            if size > limit:
                logger.warning("payload.too_large", size=size)
                return await _send_json(send, 413, {"error": f"Payload too large. Max {limit} bytes."})

        received = 0
        too_large = False
        replied = False

        async def counted_receive():
            nonlocal received, too_large
            if too_large:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body") or b"")
                if received > limit:
                    # Stop reading; whatever the app answers is replaced by a 413.
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal replied
            if too_large:
                if not replied:
                    replied = True
                    logger.warning("payload.too_large_streamed", received=received)
                    await _send_json(send, 413, {"error": f"Payload too large. Max {limit} bytes."})
                return
            await send(message)

        try:
            await self.app(scope, counted_receive, guarded_send)
        except Exception:
            if not too_large:
                raise
        if too_large and not replied:
            await _send_json(send, 413, {"error": f"Payload too large. Max {limit} bytes."})


_stream_count: Dict[str, int] = defaultdict(int)
_stream_lock = asyncio.Lock()


class StreamAbuseMiddleware:
    """Caps concurrent NDJSON streams per client; a slot is held until the
    response body has been fully sent (or the client disconnects)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not path.startswith(STREAM_PREFIXES) or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        client = _client_ip(scope)
        async with _stream_lock:
            if _stream_count[client] >= MAX_STREAMS_PER_IP:
                logger.warning("stream.too_many", ip=client)
                return await _send_json(send, 429, {"error": "Too many open requests. Let one finish first."})
            _stream_count[client] += 1
        try:
            await self.app(scope, receive, send)
        finally:
            async with _stream_lock:
                _stream_count[client] -= 1
                if _stream_count[client] <= 0:
                    _stream_count.pop(client, None)
