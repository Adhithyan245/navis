"""The registered agents. Import `registry` (not the individual modules) to
dispatch; adding an agent = add it here."""
from __future__ import annotations

from apps.api.agentic.core_agents import LOCATION, TECH_COMMUNITY
from apps.api.agentic.domain_agents import DOMAIN_AGENTS
from apps.api.agentic.registry import agent_registry as registry
from apps.api.agentic.support_agents import NARRATOR, VOICE
from apps.api.agentic.workflow_agents import WORKFLOW_AGENTS

for _agent in (LOCATION, *WORKFLOW_AGENTS, TECH_COMMUNITY, *DOMAIN_AGENTS, VOICE, NARRATOR):
    registry.register(_agent)

__all__ = ["registry", "LOCATION", "NARRATOR", "VOICE"]
