"""
Agent registry endpoint.

This is the single source of truth for which backend domains are
user-facing agents. It is a CURATED manifest — not a raw filesystem
scan — so internal routes (health, ops, interaction, onboard) are
intentionally excluded.

To add a new agent:
  1. Add an entry to AGENT_MANIFEST below
  2. Ensure the corresponding route file exists in routes/
  3. Run: npm run sync:agents (from apps/web)
"""

from fastapi import APIRouter
from typing import List
from pydantic import BaseModel

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentEntry(BaseModel):
    id: str          # lowercase, matches URL path and route file name
    name: str        # PascalCase display name
    description: str
    href: str        # frontend path: "/id"


class AgentListResponse(BaseModel):
    agents: List[AgentEntry]


# ---------------------------------------------------------------------------
# Curated agent manifest — edit this list to add/remove user-facing agents.
# Ordering here determines display order in the UI.
# ---------------------------------------------------------------------------
AGENT_MANIFEST: List[AgentEntry] = [
    AgentEntry(
        id="taste",
        name="Taste",
        description="Discover places based on your preferences",
        href="/taste",
    ),
    AgentEntry(
        id="settle",
        name="Settle",
        description="Manage your move-in essentials",
        href="/settle",
    ),
    AgentEntry(
        id="explore",
        name="Explore",
        description="Find events and local deals",
        href="/explore",
    ),
    AgentEntry(
        id="transit",
        name="Transit",
        description="Navigate your city efficiently",
        href="/transit",
    ),
    AgentEntry(
        id="connect",
        name="Connect",
        description="Build your local network",
        href="/connect",
    ),
    AgentEntry(
        id="move",
        name="Move",
        description="Plan and coordinate your relocation",
        href="/move",
    ),
    AgentEntry(
        id="services",
        name="Services",
        description="Find trusted local services",
        href="/services",
    ),
    AgentEntry(
        id="work",
        name="Work",
        description="Discover jobs and workspaces near you",
        href="/work",
    ),
    AgentEntry(
        id="voice",
        name="Voice",
        description="Speak with your assistant",
        href="/voice",
    ),
]


@router.get("/list", response_model=AgentListResponse)
async def list_agents():
    """
    Returns the curated list of user-facing agents.
    Used by the frontend sync script and as a runtime registry source.
    """
    return AgentListResponse(agents=AGENT_MANIFEST)
