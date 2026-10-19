"""
Routing: which agents handle a request.

Rules first (no latency, no cost):
  * workflow agents via the existing RuleBasedIntentAnalyzer
    (runtime/intent/analyzer.py), mapped workflow → agent
  * direct agents via their manifest `triggers`, scored the same way

Only when rules land on nothing but the default fallback does a small LLM
planner (settings.GROQ_FAST_MODEL) pick agents from the registry's
descriptions. Its answer is validated against the registry and cached.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp

from apps.api.agentic.base import Agent
from apps.api.agentic.registry import AgentRegistry
from apps.api.core.config import settings
from apps.api.core.logging import get_logger
from apps.api.runtime.intent.analyzer import _matches, _normalize, intent_analyzer
from apps.api.services.cache.ttl_cache import cache

logger = get_logger(__name__)

INCLUSION_THRESHOLD = 0.45
MAX_AGENTS = 4
_PLANNER_URL = "https://api.groq.com/openai/v1/chat/completions"
_PLANNER_TIMEOUT = aiohttp.ClientTimeout(total=4.0)


@dataclass
class RoutePlan:
    agents: List[Agent] = field(default_factory=list)
    reasons: Dict[str, str] = field(default_factory=dict)
    planner: str = "rules"   # rules | llm | fallback

    @property
    def workflow_agents(self) -> List[Agent]:
        return [a for a in self.agents if a.manifest.workflow]

    @property
    def direct_agents(self) -> List[Agent]:
        return [a for a in self.agents if not a.manifest.workflow]


def _score(agent: Agent, normalized: str) -> float:
    score = sum(w for kw, w in agent.manifest.triggers if _matches(kw, normalized))
    return 0.0 if score <= 0 else 1.0 - 1.0 / (1.0 + score)


async def _llm_plan(query: str, registry: AgentRegistry) -> Optional[List[str]]:
    if not settings.GROQ_API_KEY:
        return None
    key = f"agentic.plan:{_normalize(query)}"
    cached = await cache.get(key)
    if cached is not None:
        return cached or None
    catalog = "\n".join(f"- {m.name}: {m.description}" for m in registry.manifests() if m.user_facing)
    prompt = (
        "You route a city-companion app's requests to specialist agents.\n"
        f"Agents:\n{catalog}\n\n"
        f'Request: "{query}"\n'
        'Reply with JSON only: {"agents": ["name", ...]} with 1-3 agent names, most relevant '
        'first, or {"agents": []} if none of them fit.'
    )
    payload = {"model": settings.GROQ_FAST_MODEL, "temperature": 0, "max_tokens": 300,
               "reasoning_effort": "low", "response_format": {"type": "json_object"},
               "messages": [{"role": "user", "content": prompt}]}
    try:
        async with aiohttp.ClientSession(timeout=_PLANNER_TIMEOUT) as session:
            async with session.post(_PLANNER_URL, json=payload,
                                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        content = data["choices"][0]["message"]["content"]
        names = [n for n in json.loads(content).get("agents", []) if isinstance(n, str)]
    except Exception as exc:  # noqa: BLE001
        logger.info("agentic.planner.unavailable", error=str(exc))
        return None
    valid = [n for n in names if (a := registry.get(n)) and a.manifest.user_facing][:3]
    await cache.set(key, valid, ttl=3600)
    return valid or None


async def route(query: str, user_context: Dict, registry: AgentRegistry) -> RoutePlan:
    plan = RoutePlan()
    normalized = _normalize(query)

    # 1. Direct agents by manifest triggers
    direct_scores = {
        a.name: _score(a, normalized)
        for a in registry.all()
        if not a.manifest.workflow and a.manifest.user_facing and a.manifest.triggers
    }
    direct_hits = sorted(((s, n) for n, s in direct_scores.items() if s >= INCLUSION_THRESHOLD), reverse=True)

    # 2. Workflow agents by the runtime intent rules
    matches = await intent_analyzer.analyze(query, user_context)
    only_fallback = len(matches) == 1 and "fallback" in matches[0].reason
    workflow_hits = []
    for m in matches:
        agent = registry.by_workflow(m.workflow)
        if agent is None:
            continue
        if only_fallback and direct_hits:
            continue  # a direct agent matched; don't pad with the generic default
        workflow_hits.append((m.confidence, agent, m.reason))

    # A tech ask shouldn't also pull the general ticketed-events agent unless
    # it scores higher there.
    tech = direct_scores.get("tech_community", 0.0)
    if tech >= INCLUSION_THRESHOLD:
        workflow_hits = [h for h in workflow_hits
                         if not (h[1].manifest.workflow == "connect_mode" and h[0] <= tech)]

    ranked = [(conf, agent, f"{reason} ({conf:.2f})") for conf, agent, reason in workflow_hits]
    ranked += [(score, registry.get(name), f"triggers ({score:.2f})") for score, name in direct_hits]
    ranked.sort(key=lambda r: r[0], reverse=True)
    for _, agent, reason in ranked:
        plan.agents.append(agent)
        plan.reasons[agent.name] = reason

    # 3. Nothing but the generic default → let the planner try
    if only_fallback and not direct_hits:
        names = await _llm_plan(query, registry)
        if names:
            plan.agents = [registry.get(n) for n in names]
            plan.reasons = {n: "llm planner" for n in names}
            plan.planner = "llm"
        else:
            plan.planner = "fallback"

    # Highest-priority first, capped.
    seen, ordered = set(), []
    for a in plan.agents:
        if a and a.name not in seen:
            seen.add(a.name)
            ordered.append(a)
    plan.agents = ordered[:MAX_AGENTS]
    return plan
