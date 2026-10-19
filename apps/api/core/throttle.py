"""
One Nominatim throttle for the whole deployment.

The public OSM Nominatim allows ~1 request/second per application. All
callers (search autocomplete, reverse geocoding, map place details) go
through `nominatim_slot()`; with REDIS_URL set the spacing is shared by
every worker and instance, otherwise it's per process. Point
NOMINATIM_URL at a self-hosted or commercial Nominatim and set
NOMINATIM_MIN_INTERVAL_S=0 to lift the limit.
"""
from __future__ import annotations

import asyncio
import time

from apps.api.core import kv
from apps.api.core.config import settings

_lock = asyncio.Lock()
_last = 0.0


class NominatimBusy(Exception):
    pass


async def _redis_slot(interval_ms: int) -> bool:
    client = kv.redis_state.client()
    if client is None:
        return True
    try:
        return bool(await client.set("navis:nominatim:slot", b"1", nx=True, px=interval_ms))
    except Exception as exc:  # noqa: BLE001
        kv.redis_state.failed(exc)
        return True


async def nominatim_slot(*, skip_if_busy: bool = False, max_wait_s: float = 4.0) -> None:
    """Wait for our turn. With skip_if_busy (autocomplete), raise
    NominatimBusy instead of queueing behind another call."""
    global _last
    interval = settings.NOMINATIM_MIN_INTERVAL_S
    if interval <= 0:
        return
    if skip_if_busy and _lock.locked():
        raise NominatimBusy()
    async with _lock:
        loop = asyncio.get_running_loop()
        wait = interval - (loop.time() - _last)
        if wait > 0:
            await asyncio.sleep(wait)
        deadline = time.monotonic() + max_wait_s
        while not await _redis_slot(int(interval * 1000)):
            if skip_if_busy or time.monotonic() > deadline:
                raise NominatimBusy()
            await asyncio.sleep(0.2)
        _last = loop.time()
