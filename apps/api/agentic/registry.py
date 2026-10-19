"""AgentRegistry — the catalog of agents the supervisor can dispatch to."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from apps.api.agentic.base import Agent, AgentManifest


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, Agent] = {}

    def register(self, agent: Agent) -> Agent:
        name = agent.manifest.name
        if name in self._agents and self._agents[name] is not agent:
            raise ValueError(f"agent {name!r} already registered")
        self._agents[name] = agent
        return agent

    def get(self, name: str) -> Optional[Agent]:
        return self._agents.get(name)

    def all(self) -> List[Agent]:
        return list(self._agents.values())

    def manifests(self) -> List[AgentManifest]:
        return [a.manifest for a in self._agents.values()]

    def by_workflow(self, workflow: str) -> Optional[Agent]:
        for a in self._agents.values():
            if a.manifest.workflow == workflow:
                return a
        return None

    def names(self) -> Iterable[str]:
        return self._agents.keys()


agent_registry = AgentRegistry()
