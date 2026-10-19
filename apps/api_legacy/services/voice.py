"""
Voice / NLU service — powers Voice and Ask Native agents.

When OPENAI_API_KEY is set:
  - Uses GPT-4o-mini to parse natural language intent
  - Returns structured {intent, agent, query, confidence}

When OPENAI_API_KEY is missing:
  - Falls back to keyword-based routing (no external calls)
  - Covers the most common user intents reliably

Intent → Agent mapping:
  food / restaurant / eat / taste → taste
  event / concert / meetup / connect → connect
  transit / subway / bus / commute / move → transit
  work / job / career / coworking → work
  hospital / pharmacy / doctor / service → services
  settle / move in / housing / apartment → settle
  explore / discover / places → explore
  (default) → explore
"""

import logging
from typing import Dict, Any
from core.config import settings

logger = logging.getLogger(__name__)

# Keyword → agent routing table (used as fallback when OpenAI unavailable)
_KEYWORD_RULES = [
    (["food", "restaurant", "eat", "taste", "cuisine", "dinner", "lunch", "breakfast", "cafe", "coffee"], "taste"),
    (["event", "concert", "festival", "meetup", "connect", "networking", "show", "gig", "party"], "connect"),
    (["transit", "subway", "bus", "commute", "mbta", "train", "route", "directions", "move around"], "transit"),
    (["job", "work", "career", "coworking", "office", "employment", "hiring", "remote"], "work"),
    (["hospital", "doctor", "pharmacy", "clinic", "urgent care", "dentist", "service", "medical"], "services"),
    (["settle", "move in", "housing", "apartment", "rent", "neighborhood", "utilities"], "settle"),
    (["explore", "discover", "places", "things to do", "attractions", "sightseeing"], "explore"),
]

_AGENT_QUERY_EXTRACT = {
    "taste": lambda t: t,
    "connect": lambda t: t,
    "transit": lambda t: t,
    "work": lambda t: t,
    "services": lambda t: t,
    "settle": lambda t: t,
    "explore": lambda t: t,
}


def _keyword_parse(transcript: str) -> Dict[str, Any]:
    """Fast keyword-based intent routing — no external calls."""
    lower = transcript.lower()
    for keywords, agent in _KEYWORD_RULES:
        if any(kw in lower for kw in keywords):
            return {
                "intent": agent,
                "agent": agent,
                "query": transcript,
                "confidence": 0.7,
                "method": "keyword",
            }
    return {
        "intent": "explore",
        "agent": "explore",
        "query": transcript,
        "confidence": 0.4,
        "method": "keyword_default",
    }


class VoiceService:
    """
    Intent parser for Voice / Ask Native agent.
    Uses Local LLM (Ollama) when available, keyword fallback otherwise.
    """

    _SYSTEM_PROMPT = """You are an intent classifier for a city intelligence app called Navis.
The user's message is a natural language query. Classify it into exactly one of these agents:
taste, connect, transit, work, services, settle, explore

Respond ONLY with a JSON object in this exact format:
{"intent": "<agent>", "agent": "<agent>", "query": "<cleaned query>", "confidence": <0.0-1.0>}

- intent and agent must be the same value
- query should be the user's request cleaned up for API use
- confidence is your certainty (0.0 to 1.0)
"""

    async def parse_intent(self, transcript: str, city: str = "") -> Dict[str, Any]:
        """
        Parse natural language transcript into a structured agent intent.
        Returns dict with: intent, agent, query, confidence, method
        """
        if not transcript or not transcript.strip():
            return {
                "intent": "explore",
                "agent": "explore",
                "query": "",
                "confidence": 0.0,
                "method": "empty_input",
            }

        try:
            from services.local_llm import LocalLLMProvider
            import json

            llm_provider = LocalLLMProvider()
            context_hint = f" The user is in {city}." if city else ""
            user_message = f"{transcript}{context_hint}"

            response_text = await llm_provider.generate_response(user_message, system=self._SYSTEM_PROMPT)

            if response_text:
                parsed = json.loads(response_text)

                # Validate agent field
                valid_agents = {"taste", "connect", "transit", "work", "services", "settle", "explore"}
                if parsed.get("agent") not in valid_agents:
                    logger.warning("Local LLM returned unknown agent '%s', falling back.", parsed.get("agent"))
                    return _keyword_parse(transcript)

                parsed["method"] = "local_llm"
                return parsed

            logger.warning("Local LLM returned empty — falling back to keyword routing.")
            return _keyword_parse(transcript)

        except Exception as e:
            logger.warning("Local LLM intent parsing failed (%s) — using keyword fallback.", e)
            return _keyword_parse(transcript)
