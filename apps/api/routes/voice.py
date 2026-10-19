"""
POST /v2/voice — speech-to-text for the voice query flow.

Accepts a multipart/form-data POST with an `audio` field, transcribes it
with Groq Whisper (services/transcription.py) and returns the transcript.
The frontend puts the transcript in the query box and runs it through
/v2/query; this route does not run the query itself.

Responses:
  200 {"status": "transcribed", "transcript": "...", ...}
  200 {"status": "no_speech", "transcript": "", ...}   clip had no words
  413 audio over the 25 MiB cap
  422 the STT provider couldn't decode the clip
  502 STT provider failed
  503 transcription not configured (no GROQ_API_KEY)

Error bodies are short, client-safe messages; provider errors and
exception text only go to the logs.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile

from apps.api.core.logging import get_logger
from apps.api.agentic.catalog import VOICE
from apps.api.services.transcription import TranscriptionError

logger = get_logger(__name__)
router = APIRouter(prefix="/v2")


# Hard limit so a slow upload can't pin a worker forever. 25 MiB matches
# Groq's (and most STT providers') file limit and keeps memory predictable.
_MAX_AUDIO_BYTES = 25 * 1024 * 1024

_ERRORS = {
    "not_configured": (503, "Voice transcription isn't configured on the server."),
    "rejected": (422, "That recording couldn't be transcribed. Try recording again."),
    "unavailable": (502, "Transcription is temporarily unavailable. Please try again."),
}


@router.post("/voice")
async def voice_upload(audio: UploadFile = File(...)) -> Dict[str, Any]:
    """Transcribe an uploaded audio clip."""
    # Read with bounded size — UploadFile.read() reads everything; we cap it.
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = await audio.read(64 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > _MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"audio exceeds {_MAX_AUDIO_BYTES} bytes",
            )
        chunks.append(chunk)

    logger.info(
        "voice.upload",
        bytes=received,
        content_type=audio.content_type,
        filename=audio.filename,
    )

    if received == 0:
        raise HTTPException(status_code=422, detail=_ERRORS["rejected"][1])

    try:
        transcript = await VOICE.transcribe(
            b"".join(chunks),
            filename=audio.filename or "voice.webm",
            content_type=audio.content_type,
        )
    except TranscriptionError as exc:
        status_code, message = _ERRORS.get(exc.reason, _ERRORS["unavailable"])
        raise HTTPException(status_code=status_code, detail=message)

    if not transcript:
        return {
            "status": "no_speech",
            "message": "I didn't catch any words. Try speaking a little closer to the mic.",
            "transcript": "",
            "received_bytes": received,
        }

    return {
        "status": "transcribed",
        "message": "Transcribed.",
        "transcript": transcript,
        "received_bytes": received,
    }
