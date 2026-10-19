"""
Speech-to-text via Groq's OpenAI-compatible Whisper endpoint.

`transcribe()` returns the transcript text (possibly "" when the clip had no
speech) or raises TranscriptionError with a short, client-safe reason code.
Upstream error bodies and exception text are logged, never returned.
"""
from __future__ import annotations

import aiohttp

from apps.api.core.config import settings
from apps.api.core.logging import get_logger

logger = get_logger(__name__)

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_TIMEOUT = aiohttp.ClientTimeout(total=60)


class TranscriptionError(Exception):
    """`reason` is one of: not_configured, rejected, unavailable."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def transcribe(audio: bytes, *, filename: str, content_type: str | None) -> str:
    if not settings.GROQ_API_KEY:
        raise TranscriptionError("not_configured")

    form = aiohttp.FormData()
    form.add_field("file", audio, filename=filename,
                   content_type=content_type or "application/octet-stream")
    form.add_field("model", settings.GROQ_STT_MODEL)
    form.add_field("response_format", "json")
    form.add_field("temperature", "0")

    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(GROQ_TRANSCRIPTION_URL, data=form, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return str((data or {}).get("text") or "").strip()
                body = (await resp.text())[:300]
                logger.warning("stt.groq.bad_status", status=resp.status, body=body)
                # 400/413/415: Groq couldn't decode or accept this clip.
                if resp.status in (400, 413, 415, 422):
                    raise TranscriptionError("rejected")
                raise TranscriptionError("unavailable")
    except TranscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("stt.groq.error", error=str(exc))
        raise TranscriptionError("unavailable") from exc
