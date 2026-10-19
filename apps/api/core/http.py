"""
Shared, pooled aiohttp session for outbound API calls (one per event
loop), so hot paths reuse connections and TLS sessions instead of opening
a new client per call. Pass a per-request `timeout=` where it matters.
"""
from __future__ import annotations

import asyncio
from typing import Dict

import aiohttp

from apps.api.core.config import settings

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=12, connect=5)
_sessions: Dict[int, aiohttp.ClientSession] = {}


def get_session() -> aiohttp.ClientSession:
    loop = asyncio.get_running_loop()
    key = id(loop)
    session = _sessions.get(key)
    if session is None or session.closed:
        # Drop sessions left behind by finished loops (tests, reloads).
        for k in [k for k, s in _sessions.items() if s.closed]:
            _sessions.pop(k, None)
        connector = aiohttp.TCPConnector(limit=max(settings.MAX_CONCURRENCY * 5, 100), limit_per_host=20,
                                         ttl_dns_cache=300, enable_cleanup_closed=True)
        session = aiohttp.ClientSession(connector=connector, timeout=DEFAULT_TIMEOUT)
        _sessions[key] = session
    return session


async def close_sessions() -> None:
    for key, session in list(_sessions.items()):
        if not session.closed:
            await session.close()
        _sessions.pop(key, None)
