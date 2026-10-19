"""POST /v2/voice — Groq Whisper transcription (provider call mocked)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routes import voice
from apps.api.agentic import support_agents
from apps.api.services import transcription
from apps.api.services.transcription import TranscriptionError

client = TestClient(app)


def _post(data: bytes = b"RIFF fake wav bytes", content_type: str = "audio/webm"):
    return client.post(
        "/v2/voice",
        files={"audio": ("clip.webm", data, content_type)},
    )


def test_transcribed_clip_returns_transcript():
    mock = AsyncMock(return_value="coffee shops near Boston Common")
    with patch.object(support_agents, "transcribe", mock):
        resp = _post()
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "transcribed"
    assert body["transcript"] == "coffee shops near Boston Common"
    _, kwargs = mock.call_args
    assert kwargs["filename"] == "clip.webm"
    assert kwargs["content_type"] == "audio/webm"


def test_silent_clip_reports_no_speech():
    with patch.object(support_agents, "transcribe", AsyncMock(return_value="")):
        resp = _post()
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_speech"
    assert resp.json()["transcript"] == ""


@pytest.mark.parametrize("reason,status", [
    ("not_configured", 503),
    ("rejected", 422),
    ("unavailable", 502),
])
def test_provider_failures_map_to_scrubbed_errors(reason, status):
    with patch.object(support_agents, "transcribe", AsyncMock(side_effect=TranscriptionError(reason))):
        resp = _post()
    assert resp.status_code == status
    # Only the fixed, client-safe message crosses the wire.
    assert resp.json()["detail"] == voice._ERRORS[reason][1]


def test_empty_upload_is_rejected_without_calling_provider():
    mock = AsyncMock(return_value="x")
    with patch.object(support_agents, "transcribe", mock):
        resp = _post(data=b"")
    assert resp.status_code == 422
    mock.assert_not_called()


def test_voice_accepts_uploads_over_global_payload_limit():
    # The global middleware caps bodies at 64 KB; voice must allow real clips.
    with patch.object(support_agents, "transcribe", AsyncMock(return_value="hello")):
        resp = _post(data=b"0" * 200_000)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_transcribe_without_key_is_not_configured():
    with patch.object(transcription.settings, "GROQ_API_KEY", None):
        with pytest.raises(TranscriptionError) as exc:
            await transcription.transcribe(b"x", filename="a.webm", content_type="audio/webm")
    assert exc.value.reason == "not_configured"


def test_stt_model_setting_defaults_to_whisper():
    from apps.api.core.config import Settings
    assert Settings(_env_file=None).GROQ_STT_MODEL.startswith("whisper")
