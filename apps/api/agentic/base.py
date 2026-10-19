"""
Agent contract for Navis.

Every user-facing function of the app is owned by exactly one Agent. An
agent declares a manifest (what it does, which asks it handles, how long it
may take) and implements `run(task) -> AgentResult`.

`AgentResult.message` is shown to users as-is, so it must be friendly and
positive even when there's nothing to show ("No tech meetups are listed this
week; here are online ones…"). Internal details (provider names, exception
text) belong in logs, never in `message`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

Status = Literal["ok", "partial", "empty", "unavailable"]


@dataclass(frozen=True)
class Place:
    """The resolved place a task is about."""
    lat: float
    lon: float
    name: str
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None

    def label(self) -> str:
        return self.city or self.name

    def as_dict(self) -> Dict[str, Any]:
        return {"lat": self.lat, "lon": self.lon, "name": self.name, "city": self.city,
                "country": self.country, "country_code": self.country_code, "region": self.region}


@dataclass
class AgentTask:
    query: str
    user_context: Dict[str, Any]
    place: Optional[Place] = None
    run_id: str = ""
    # Caller hints, e.g. {"window_days": 14} from the /today hub.
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    domain: str
    status: Status
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    alternatives: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def section(self, *, kind: str, title: str) -> Dict[str, Any]:
        """Wire shape: one entry of final_result.sections."""
        return {
            "kind": kind,
            "agent": self.agent,
            "title": title,
            "status": self.status,
            "message": self.message,
            "alternatives": self.alternatives,
            "data": self.data,
        }


@dataclass(frozen=True)
class AgentManifest:
    name: str                      # stable id, e.g. "tech_community"
    domain: str                    # section kind on the wire, e.g. "tech"
    title: str                     # user-facing section title
    description: str               # one line, also fed to the LLM planner
    capabilities: Tuple[str, ...] = ()
    # (keyword, weight) pairs scored like runtime/intent/analyzer.py
    triggers: Tuple[Tuple[str, float], ...] = ()
    timeout_s: float = 20.0
    needs_location: bool = True
    # Runtime workflow this agent owns (workflow-backed agents only).
    workflow: Optional[str] = None
    user_facing: bool = True


class Agent(ABC):
    manifest: AgentManifest

    @property
    def name(self) -> str:
        return self.manifest.name

    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult:
        """Do the work. May raise; the supervisor converts failures into a
        positive `unavailable` result and records metrics."""

    def result(self, status: Status, *, data: Optional[Dict[str, Any]] = None,
               message: str = "", alternatives: Sequence[str] = (),
               sources: Sequence[str] = ()) -> AgentResult:
        return AgentResult(agent=self.name, domain=self.manifest.domain, status=status,
                           data=data or {}, message=message,
                           alternatives=list(alternatives), sources=list(sources))
