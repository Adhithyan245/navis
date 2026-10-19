"""
Support agents.

  VoiceAgent     speech → text for voice questions (POST /v2/voice)
  NarratorAgent  the one-line lead for multi-agent answers ("Here's Boston
                 today: weather, tech events and getting around.")
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from apps.api.agentic import metrics
from apps.api.agentic.base import Agent, AgentManifest, AgentResult, AgentTask
from apps.api.services.transcription import TranscriptionError, transcribe


class VoiceAgent(Agent):
    manifest = AgentManifest(
        name="voice", domain="voice", title="Voice",
        description="Turns a spoken question into text.",
        needs_location=False, user_facing=False, timeout_s=60.0,
    )

    async def transcribe(self, audio: bytes, *, filename: str, content_type: Optional[str]) -> str:
        """Transcript text ("" for silence). Raises TranscriptionError."""
        started = time.monotonic()
        try:
            text = await transcribe(audio, filename=filename, content_type=content_type)
        except TranscriptionError:
            metrics.record(self.name, "error", time.monotonic() - started)
            raise
        metrics.record(self.name, "ok" if text else "empty", time.monotonic() - started)
        return text

    async def run(self, task: AgentTask) -> AgentResult:  # not routed; audio arrives via /v2/voice
        return self.result("empty", message="Send audio to transcribe.")


def _join(items: List[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" and {items[-1]}"


class NarratorAgent(Agent):
    manifest = AgentManifest(
        name="narrator", domain="narrator", title="Summary",
        description="Writes the opening line that ties a multi-part answer together.",
        needs_location=False, user_facing=False, timeout_s=2.0,
    )

    def lead(self, sections: List[Dict[str, Any]], place_label: Optional[str]) -> str:
        found = [s["title"].lower() for s in sections if s.get("status") in ("ok", "partial")]
        where = f" for {place_label}" if place_label else ""
        if found:
            return f"Here's what we found{where}: {_join(found)}."
        return (f"We're still building up listings{where}. The notes below suggest what to try next."
                if sections else "")

    async def run(self, task: AgentTask) -> AgentResult:
        return self.result("ok", data={"summary": ""})


VOICE = VoiceAgent()
NARRATOR = NarratorAgent()
