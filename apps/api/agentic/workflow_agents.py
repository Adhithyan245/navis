"""
Workflow-backed agents — each owns one runtime workflow (apps/api/workflows).

Run alone, an agent executes its workflow and reads the final payload. When
several are selected for one request, the supervisor runs their workflows
as ONE composed graph instead (shared steps like geocoding run once) and
asks each agent to interpret its section via `interpret()`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from apps.api.agentic import messages
from apps.api.agentic.base import Agent, AgentManifest, AgentResult, AgentTask
from apps.api.runtime.runner import run_workflow_ndjson


async def collect_final(workflow: str, query: str, user_context: Dict[str, Any],
                        run_id: str = "") -> Optional[Dict[str, Any]]:
    """Run a workflow and return its final_result payload (None on error)."""
    final: Optional[Dict[str, Any]] = None
    async for line in run_workflow_ndjson(workflow, query, user_context, run_id=run_id or None):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "final_result":
            final = event.get("data") if isinstance(event.get("data"), dict) else {}
        elif event.get("event") == "error":
            return None
    return final


def _count(payload: Dict[str, Any]) -> int:
    for key in ("results", "candidates", "commutes", "chunks"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


class WorkflowAgent(Agent):
    def __init__(self, manifest: AgentManifest):
        assert manifest.workflow, "workflow agents need a workflow"
        self.manifest = manifest

    def interpret(self, payload: Optional[Dict[str, Any]], place_label: Optional[str]) -> AgentResult:
        """Turn a workflow payload into an AgentResult with positive copy."""
        domain = self.manifest.domain
        if payload is None:
            msg, alts = messages.unavailable(domain)
            return self.result("unavailable", message=msg, alternatives=alts)
        if _count(payload) == 0:
            msg, alts = messages.empty(domain, place_label)
            return self.result("empty", data=payload, message=msg, alternatives=alts)
        return self.result("ok", data=payload)

    async def run(self, task: AgentTask) -> AgentResult:
        payload = await collect_final(self.manifest.workflow, task.query, task.user_context, task.run_id)
        return self.interpret(payload, task.place.label() if task.place else task.user_context.get("city"))


def _is_event(item: Any) -> bool:
    """Ticketed-event shape (vs the venues connect_mode adds as context)."""
    if not isinstance(item, dict):
        return False
    return bool(item.get("dates") or item.get("classifications") or item.get("title")
                or (item.get("_embedded") or {}).get("venues"))


class EventsWorkflowAgent(WorkflowAgent):
    """connect_mode fuses events with nearby venues; only events count, so a
    place with no listings gets the positive empty message, not cafés."""

    def interpret(self, payload, place_label):
        if payload is not None:
            events = [r for r in payload.get("results") or [] if _is_event(r)]
            payload = {**payload, "results": events}
        return super().interpret(payload, place_label)


# ── The workflow agents (intent rules live in runtime/intent/analyzer.py) ──

PLACES = WorkflowAgent(AgentManifest(
    name="places", domain="explore", title="Places to explore",
    description="Restaurants, cafés, sights and things to do near a place.",
    capabilities=("dining", "cafes", "attractions"), workflow="explore_city", timeout_s=40.0,
))
WORK = WorkflowAgent(AgentManifest(
    name="work_study", domain="work", title="Work-friendly spots",
    description="Coworking spaces, laptop-friendly cafés and study spots.",
    capabilities=("coworking", "wifi cafes", "libraries"), workflow="work_mode", timeout_s=40.0,
))
LIVE_EVENTS = EventsWorkflowAgent(AgentManifest(
    name="live_events", domain="events", title="Events happening near you",
    description="Concerts, shows, sports, nightlife and other ticketed events.",
    capabilities=("concerts", "sports", "theatre", "nightlife"), workflow="connect_mode", timeout_s=40.0,
))
NEIGHBORHOODS = WorkflowAgent(AgentManifest(
    name="neighborhoods", domain="neighborhoods", title="Neighborhoods to consider",
    description="Which areas fit a household, budget and commute.",
    capabilities=("where to live", "areas"), workflow="neighborhood_match", timeout_s=45.0,
))
COMMUTE = WorkflowAgent(AgentManifest(
    name="commute", domain="commute", title="Getting there",
    description="Travel time and distance between two places by car, bike and on foot.",
    capabilities=("routing", "travel time"), workflow="commute_analysis", timeout_s=40.0,
))
MOVE_PLAN = WorkflowAgent(AgentManifest(
    name="move_plan", domain="plan", title="Your move plan",
    description="A phased plan for moving to a place: before, first week, first months.",
    capabilities=("relocation", "timeline"), workflow="relocation_plan", timeout_s=80.0,
))
ESSENTIALS = WorkflowAgent(AgentManifest(
    name="essentials", domain="checklist", title="Essentials checklist",
    description="Must-dos for newcomers: transit card, SIM, registration, banking, healthcare.",
    capabilities=("checklist", "settling in"), workflow="essentials_checklist", timeout_s=80.0,
))

WORKFLOW_AGENTS = (PLACES, WORK, LIVE_EVENTS, NEIGHBORHOODS, COMMUTE, MOVE_PLAN, ESSENTIALS)

# section_kind (workflow metadata) → agent, for interpreting composed runs.
BY_SECTION_KIND = {a.manifest.domain: a for a in WORKFLOW_AGENTS}
