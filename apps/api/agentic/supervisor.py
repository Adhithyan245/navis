"""
Supervisor — the orchestrator behind POST /v2/query.

  1. route()         pick agents (rules first, LLM planner fallback)
  2. LocationAgent   resolve the place once for everyone
  3. execute         workflow-backed agents as ONE composed runtime graph
                     (shared geocoding/provider steps dedupe), direct agents
                     concurrently — each with its own timeout + breaker
  4. stream          partial_result as pieces finish, then one final_result
                     with `sections` (each: kind, agent, title, status,
                     message, alternatives, data)

Wire contract unchanged: only partial_result / final_result /
stream_heartbeat / error leave this module. Routing decisions, agent names
in logs, timings and failures stay internal.

Backward compatibility: when only workflow-backed agents are selected the
composed runtime stream passes through untouched (same payloads as before).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

import orjson

from apps.api.agentic import messages, metrics
from apps.api.agentic.base import Agent, AgentResult, AgentTask, Place
from apps.api.agentic.catalog import LOCATION, NARRATOR, registry
from apps.api.agentic.router import RoutePlan, route
from apps.api.agentic.workflow_agents import BY_SECTION_KIND, WorkflowAgent
from apps.api.core.logging import get_logger
from apps.api.runtime.intent import IntentAnalyzer, IntentMatch
from apps.api.runtime.runner import run_query_ndjson

logger = get_logger(__name__)

HEARTBEAT_S = 5.0


def _line(event: str, data: Any) -> bytes:
    return orjson.dumps({"event": event, "data": data}) + b"\n"


class _FixedAnalyzer(IntentAnalyzer):
    """Hands the runtime exactly the workflows the router chose."""

    def __init__(self, workflows: List[str]):
        self._workflows = workflows

    async def analyze(self, query: str, user_context: Optional[Mapping[str, Any]] = None) -> List[IntentMatch]:
        return [IntentMatch(workflow=w, confidence=1.0, reason="supervisor") for w in self._workflows]


def _interpret_workflow_final(final: Optional[Dict[str, Any]], agents: List[Agent],
                              place_label: Optional[str]) -> List[AgentResult]:
    """Map the composed (or single) workflow payload back to per-agent results."""
    results: List[AgentResult] = []
    if final is None:
        for a in agents:
            results.append(a.interpret(None, place_label))  # type: ignore[attr-defined]
        return results
    if "sections" in final and isinstance(final["sections"], list):
        by_kind = {s.get("kind"): s.get("data") for s in final["sections"] if isinstance(s, dict)}
        for a in agents:
            data = by_kind.get(a.manifest.domain)
            results.append(a.interpret(data if isinstance(data, dict) else None, place_label))  # type: ignore[attr-defined]
        return results
    # single workflow → the payload itself
    return [agents[0].interpret(final, place_label)]  # type: ignore[attr-defined]


async def _run_direct(agent: Agent, task: AgentTask) -> AgentResult:
    domain = agent.manifest.domain
    if metrics.is_open(agent.name):
        metrics.record(agent.name, "skipped", 0.0)
        msg, alts = messages.unavailable(domain)
        return agent.result("unavailable", message=msg, alternatives=alts)
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(agent.run(task), timeout=agent.manifest.timeout_s)
        metrics.record(agent.name, result.status, time.monotonic() - started)
        return result
    except asyncio.TimeoutError:
        outcome = "timeout"
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("agentic.agent_failed", agent=agent.name, error=str(exc), run_id=task.run_id)
        outcome = "error"
    metrics.record(agent.name, outcome, time.monotonic() - started)
    msg, alts = messages.unavailable(domain)
    return agent.result("unavailable", message=msg, alternatives=alts)


def _record_workflow_metrics(agents: List[Agent], final: Optional[Dict[str, Any]], seconds: float,
                             place_label: Optional[str]) -> None:
    if not agents:
        return
    for r in _interpret_workflow_final(final, agents, place_label):
        metrics.record(r.agent, r.status if final is not None else "error", seconds)


async def run_agents_ndjson(
    query: str,
    user_context: Optional[Dict[str, Any]] = None,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    agents: Optional[List[str]] = None,
) -> AsyncIterator[bytes]:
    """`agents`: run exactly these (by name) instead of routing, e.g. the
    /today hub. Unknown or non-user-facing names are ignored."""
    user_context = user_context or {}
    run_id = run_id or uuid.uuid4().hex
    if agents is not None:
        chosen = [a for n in agents if (a := registry.get(n)) and a.manifest.user_facing]
        plan = RoutePlan(agents=chosen, reasons={a.name: "explicit" for a in chosen}, planner="explicit")
    else:
        plan = await route(query, user_context, registry)
    logger.info("agentic.route", run_id=run_id, planner=plan.planner,
                agents=[a.name for a in plan.agents], reasons=plan.reasons)

    workflow_agents = plan.workflow_agents
    direct_agents = plan.direct_agents
    if not plan.agents:
        # Router found nothing at all: the default places agent still answers.
        workflow_agents = [BY_SECTION_KIND["explore"]]

    # ── Workflow-only: pass the composed runtime stream straight through ──
    if not direct_agents:
        started = time.monotonic()
        final: Optional[Dict[str, Any]] = None
        async for line in run_query_ndjson(
            query, user_context,
            analyzer=_FixedAnalyzer([a.manifest.workflow for a in workflow_agents]),
            metadata=metadata, run_id=run_id,
        ):
            try:
                ev = json.loads(line)
                if ev.get("event") == "final_result":
                    final = ev.get("data")
            except ValueError:
                pass
            yield line
        _record_workflow_metrics(workflow_agents, final, time.monotonic() - started,
                                 user_context.get("city"))
        return

    # ── Mixed: direct agents alongside the composed workflow run ──────────
    place: Optional[Place] = None
    try:
        place = await asyncio.wait_for(LOCATION.resolve(query, user_context), LOCATION.manifest.timeout_s)
    except Exception as exc:  # noqa: BLE001
        logger.info("agentic.location_unresolved", run_id=run_id, error=str(exc))
    task = AgentTask(query=query, user_context=user_context, place=place, run_id=run_id,
                     options=dict((metadata or {}).get("agent_options") or {}))
    place_label = place.label() if place else user_context.get("city")

    direct_tasks: Dict[asyncio.Task, Agent] = {
        asyncio.create_task(_run_direct(a, task), name=f"agent:{a.name}:{run_id}"): a
        for a in direct_agents
    }
    direct_results: Dict[str, AgentResult] = {}
    workflow_final: Optional[Dict[str, Any]] = None
    workflow_started = time.monotonic()

    queue: asyncio.Queue = asyncio.Queue()

    async def pump_workflows() -> None:
        nonlocal workflow_final
        if not workflow_agents:
            return
        try:
            async for line in run_query_ndjson(
                query, user_context,
                analyzer=_FixedAnalyzer([a.manifest.workflow for a in workflow_agents]),
                metadata=metadata, run_id=run_id,
            ):
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("event") == "final_result":
                    workflow_final = ev.get("data") if isinstance(ev.get("data"), dict) else {}
                elif ev.get("event") == "partial_result":
                    await queue.put(line)
                # heartbeats/errors from the inner run aren't forwarded; this
                # stream sends its own heartbeats and decides the outcome.
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("agentic.workflows_failed", run_id=run_id, error=str(exc))

    pump = asyncio.create_task(pump_workflows(), name=f"agent-workflows:{run_id}")
    pending = set(direct_tasks) | {pump}
    try:
        while pending:
            done, pending = await asyncio.wait(pending, timeout=HEARTBEAT_S,
                                               return_when=asyncio.FIRST_COMPLETED)
            while not queue.empty():
                yield queue.get_nowait()
            if not done:
                yield _line("stream_heartbeat", {})
                continue
            for t in done:
                agent = direct_tasks.get(t)
                if agent is None:
                    continue
                result = t.result()
                direct_results[agent.name] = result
                yield _line("partial_result", {
                    "section": result.section(kind=agent.manifest.domain, title=agent.manifest.title),
                    "status": "agent_done",
                })
        while not queue.empty():
            yield queue.get_nowait()
    finally:
        for t in pending:
            t.cancel()

    sections: List[Dict[str, Any]] = []
    if workflow_agents:
        _record_workflow_metrics(workflow_agents, workflow_final,
                                 time.monotonic() - workflow_started, place_label)
        for agent, result in zip(workflow_agents,
                                 _interpret_workflow_final(workflow_final, workflow_agents, place_label)):
            sections.append(result.section(kind=agent.manifest.domain, title=agent.manifest.title))
    for agent in direct_agents:
        r = direct_results.get(agent.name)
        if r is not None:
            sections.append(r.section(kind=agent.manifest.domain, title=agent.manifest.title))

    # Lead with whatever has content; positive empties follow.
    order = {"ok": 0, "partial": 1, "empty": 2, "unavailable": 3}
    sections.sort(key=lambda s: order.get(s["status"], 9))
    yield _line("final_result", {
        "query": query,
        "place": place.as_dict() if place else None,
        "summary": NARRATOR.lead(sections, place_label) if len(sections) > 1 else None,
        "sections": sections,
    })
