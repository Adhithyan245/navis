"""
SSRF guard for fetching URLs we didn't choose (e.g. websites an AI model
suggested). Only public http(s) hosts on standard ports are allowed, and
redirects are followed by hand so every hop is re-checked.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Optional
from urllib.parse import urljoin, urlsplit

import aiohttp

_MAX_HOPS = 3


async def is_public_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return False
    if parts.port not in (None, 80, 443):
        return False
    host = parts.hostname
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global or ip.is_multicast:
            return False
    return True


async def safe_status(session: aiohttp.ClientSession, url: str, *, method: str = "HEAD") -> Optional[int]:
    """Final HTTP status for `url`, following up to 3 redirects, each to a
    public host. None if any hop is disallowed or the request fails."""
    for _ in range(_MAX_HOPS + 1):
        if not await is_public_url(url):
            return None
        try:
            async with session.request(method, url, allow_redirects=False,
                                       headers={"User-Agent": "Navis/1.0 (link check)"}) as resp:
                if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
                    url = urljoin(url, resp.headers["Location"])
                    continue
                if resp.status == 405 and method == "HEAD":
                    method = "GET"
                    continue
                return resp.status
        except Exception:  # noqa: BLE001
            return None
    return None
