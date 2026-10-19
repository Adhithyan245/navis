"""
Domain agents over services/domain/*: one function each.

  weather          forecast, daylight, what to pack
  money            local currency, exchange rate, tipping
  safety_health    emergency numbers, hospitals, pharmacies, police
  transit          getting around: stations/stops by mode + local card tip
  arrival          airports, rail/ferry terminals, local time
  local_knowledge  overview, customs and handy phrases

Local tips (transit card, tipping) come from an already-generated place
guide when one is cached; agents never wait on generating one.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from apps.api.agentic.base import Agent, AgentManifest, AgentResult, AgentTask, Place
from apps.api.services import place_guide
from apps.api.services.domain.arrival import arrival
from apps.api.services.domain.common import PlaceRef
from apps.api.services.domain.local_knowledge import local_knowledge
from apps.api.services.domain.money import money
from apps.api.services.domain.safety_health import safety_health
from apps.api.services.domain.transit import transit
from apps.api.services.domain.weather import weather


def _ref(place: Place) -> PlaceRef:
    return PlaceRef(lat=place.lat, lon=place.lon, city=place.city or place.name, country=place.country,
                    country_code=place.country_code, region=place.region)


def _guide_tip(place: Place, topics: tuple[str, ...]) -> Optional[str]:
    """First cached place-guide item on one of `topics` (no generation)."""
    items = place_guide._read_cache(place_guide.place_key(place.city or place.name, place.country_code)) or []
    for item in items:
        tags = set(item.get("frontmatter", {}).get("tags") or [])
        if tags & set(topics):
            title = item["frontmatter"].get("title")
            body = item.get("body") or ""
            return f"{title}. {body}".strip() if body else title
    return None


class DomainAgent(Agent):
    def __init__(self, manifest: AgentManifest, call: Callable[[Place, AgentTask], Any]):
        self.manifest = manifest
        self._call = call

    async def run(self, task: AgentTask) -> AgentResult:
        if task.place is None:
            return self.result("empty", message="Tell us which place you mean to see this.",
                               alternatives=["Set your city in your profile, or name a place in your question."])
        out: Dict[str, Any] = await self._call(task.place, task)
        return self.result(out["status"], data=out.get("data") or {}, message=out.get("message", ""),
                           alternatives=out.get("alternatives") or [], sources=out.get("sources") or [])


async def _weather(place: Place, task: AgentTask):
    return await weather(_ref(place))


async def _money(place: Place, task: AgentTask):
    home = task.user_context.get("homeCountryCode")
    return await money(_ref(place), home_country_code=home if isinstance(home, str) else None,
                       tipping=_guide_tip(place, ("money", "etiquette")))


async def _safety(place: Place, task: AgentTask):
    return await safety_health(_ref(place))


async def _transit(place: Place, task: AgentTask):
    return await transit(_ref(place), local_tip=_guide_tip(place, ("transit",)))


async def _arrival(place: Place, task: AgentTask):
    return await arrival(_ref(place))


async def _local(place: Place, task: AgentTask):
    return await local_knowledge(_ref(place))


WEATHER = DomainAgent(AgentManifest(
    name="weather", domain="weather", title="Weather",
    description="Current weather, 7-day forecast, sunrise/sunset and what to pack.",
    capabilities=("forecast", "packing"),
    triggers=(("weather", 1.2), ("forecast", 1.2), ("rain", 0.9), ("raining", 0.9), ("snow", 0.9),
              ("temperature", 1.0), ("how cold", 1.0), ("how hot", 1.0), ("sunny", 0.8), ("umbrella", 0.8),
              ("what to wear", 1.0), ("should pack", 1.0), ("what to pack", 1.0), ("pack for", 1.0),
              ("should wear", 1.0), ("climate", 0.9),
              ("humid", 0.7), ("sunset", 0.8), ("sunrise", 0.8)),
    timeout_s=12.0,
), _weather)

MONEY = DomainAgent(AgentManifest(
    name="money", domain="money", title="Money",
    description="Local currency, exchange rate from your home currency and tipping customs.",
    capabilities=("currency", "exchange rate", "tipping"),
    triggers=(("currency", 1.2), ("exchange rate", 1.2), ("exchange money", 1.1), ("money", 0.7),
              ("cash", 0.8), ("atm", 0.9), ("tipping", 1.1), ("should tip", 1.2),
              ("how much to tip", 1.2), ("pay with card", 0.8)),
    timeout_s=10.0,
), _money)

SAFETY = DomainAgent(AgentManifest(
    name="safety_health", domain="safety", title="Safety & health",
    description="Emergency numbers and the nearest hospitals, pharmacies, clinics and police.",
    capabilities=("emergency", "hospitals", "pharmacies"),
    triggers=(("emergency", 1.2), ("hospital", 1.2), ("pharmacy", 1.1), ("pharmacies", 1.1),
              ("doctor", 1.0), ("clinic", 1.0), ("urgent care", 1.2), ("police", 1.0), ("safe", 0.9),
              ("safety", 1.0), ("dangerous", 1.0), ("crime", 0.9), ("sick", 0.9), ("medicine", 0.9),
              ("ambulance", 1.2), ("911", 1.0), ("112", 1.0)),
    timeout_s=12.0,
), _safety)

TRANSIT = DomainAgent(AgentManifest(
    name="transit", domain="transit", title="Getting around",
    description="Public transport near you: metro, train, tram, bus and ferry stops, plus the local transit card.",
    capabilities=("stations", "stops", "transit card"),
    triggers=(("transit", 1.2), ("public transport", 1.2), ("metro", 1.0), ("subway", 1.0), ("bus", 0.8),
              ("buses", 0.8), ("train", 0.8), ("tram", 0.9), ("ferry", 0.9), ("get around", 1.2),
              ("getting around", 1.2), ("transport card", 1.2), ("travel card", 1.0), ("station", 0.7)),
    timeout_s=12.0,
), _transit)

ARRIVAL = DomainAgent(AgentManifest(
    name="arrival", domain="arrival", title="Getting here",
    description="Nearest airports, train and ferry terminals, and the local time zone.",
    capabilities=("airports", "terminals", "time zone"),
    triggers=(("airport", 1.2), ("fly", 0.8), ("flight", 1.0), ("flights", 1.0), ("arrive", 0.8),
              ("arriving", 0.9), ("landing", 0.8), ("get there", 0.9), ("get here", 0.9),
              ("time zone", 1.1), ("timezone", 1.1), ("local time", 1.1), ("jet lag", 1.0)),
    timeout_s=12.0,
), _arrival)

LOCAL_KNOWLEDGE = DomainAgent(AgentManifest(
    name="local_knowledge", domain="culture", title="Know before you go",
    description="A short overview of the place, local customs and etiquette, and handy phrases.",
    capabilities=("overview", "etiquette", "phrases"),
    triggers=(("history", 1.0), ("culture", 1.1), ("customs", 1.1), ("etiquette", 1.2), ("language", 1.0),
              ("phrases", 1.1), ("how do i say", 1.1), ("tell me about", 0.9), ("known for", 1.0),
              ("about the city", 0.9), ("local customs", 1.2), ("dos and don'ts", 1.2)),
    timeout_s=30.0,
), _local)

DOMAIN_AGENTS = (WEATHER, MONEY, SAFETY, TRANSIT, ARRIVAL, LOCAL_KNOWLEDGE)
