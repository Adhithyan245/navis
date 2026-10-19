"""
Direct agents (not workflow-backed).

  * LocationAgent    resolves the place a request is about, once, for every
                     other agent (the query's place, else the user's city).
  * TechCommunityAgent  tech meetups, hackathons, workshops and conferences
                     near the place (via EventsService), with online picks
                     when local listings are thin.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from apps.api.agentic import messages
from apps.api.agentic.base import Agent, AgentManifest, AgentResult, AgentTask, Place
from apps.api.services.events_service import events_service
from apps.api.services.geocoding import geocoding_service
from apps.api.services.place_extraction import find_place


def _place_from_location(loc: Dict[str, Any]) -> Optional[Place]:
    try:
        lat, lon = float(loc["lat"]), float(loc["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return Place(lat=lat, lon=lon, name=str(loc.get("name") or loc.get("city") or ""),
                 city=loc.get("city") or loc.get("name"), country=loc.get("country"),
                 country_code=(loc.get("country_code") or None), region=loc.get("region") or loc.get("state"))


class LocationAgent(Agent):
    manifest = AgentManifest(
        name="location", domain="location", title="Location",
        description="Works out which place a request is about.",
        needs_location=False, user_facing=False, timeout_s=12.0,
    )

    async def resolve(self, query: str, user_context: Dict[str, Any]) -> Optional[Place]:
        home = user_context.get("cityLocation") if isinstance(user_context.get("cityLocation"), dict) else None
        home_place = _place_from_location(home) if home else None
        named = find_place(query)
        if named and (not home_place or named.lower() not in {
                (home_place.city or "").lower(), (home_place.name or "").lower()}):
            matches = await geocoding_service.search(
                named, limit=1,
                bias_lat=home_place.lat if home_place else None,
                bias_lon=home_place.lon if home_place else None,
                city=home_place.city if home_place else None,
            )
            if matches:
                return _place_from_location(matches[0].model_dump())
        if home_place:
            return home_place
        city = user_context.get("city")
        if isinstance(city, str) and city.strip():
            matches = await geocoding_service.search(city.strip(), limit=1)
            if matches:
                return _place_from_location(matches[0].model_dump())
        return None

    async def run(self, task: AgentTask) -> AgentResult:
        place = await self.resolve(task.query, task.user_context)
        if not place:
            return self.result("empty", message="Tell us which place you mean, like a city, town or island.")
        return self.result("ok", data=place.as_dict())


_WINDOWS: Tuple[Tuple[str, int, int], ...] = (
    # (pattern, start offset days, length days)
    (r"\b(today|tonight)\b", 0, 1),
    (r"\btomorrow\b", 1, 1),
    (r"\bthis weekend\b", -1, 0),          # computed below
    (r"\b(this|next 7 days|coming) week\b", 0, 7),
    (r"\bnext week\b", 7, 7),
    (r"\bthis month\b", 0, 30),
)


def date_window(query: str, today: Optional[date] = None) -> Tuple[date, date]:
    today = today or date.today()
    q = (query or "").lower()
    for pattern, offset, length in _WINDOWS:
        if re.search(pattern, q):
            if offset == -1:  # weekend: Fri–Sun from today, else the coming Sat–Sun
                dow = today.weekday()  # Mon 0 … Sun 6
                start = today if dow >= 4 else today + timedelta(days=5 - dow)
                return start, start + timedelta(days=6 - start.weekday())
            start = today + timedelta(days=offset)
            return start, start + timedelta(days=max(length - 1, 0))
    return today, today + timedelta(days=29)


class TechCommunityAgent(Agent):
    manifest = AgentManifest(
        name="tech_community", domain="tech", title="Tech & community",
        description="Tech meetups, hackathons, workshops, startup and developer events near a place, plus online ones.",
        capabilities=("meetups", "hackathons", "conferences", "workshops"),
        triggers=(
            ("tech", 1.0), ("meetup", 0.9), ("meet up", 0.9), ("hackathon", 1.2),
            ("hackathons", 1.2), ("developer", 0.9), ("startup", 0.8), ("founder", 0.7),
            ("networking", 0.8), ("conference", 0.8), ("workshop", 0.7), ("coding", 0.9),
            ("ai", 0.6), ("ai event", 1.0), ("ai meetup", 1.2), ("machine learning", 0.9), ("devs", 0.8),
            ("community event", 0.8),
        ),
        # First request after a restart fetches every source fresh.
        timeout_s=45.0,
    )

    async def run(self, task: AgentTask) -> AgentResult:
        place = task.place
        if place is None:
            msg, alts = messages.empty("tech", None)
            return self.result("empty", message="Pick a place to see tech events there.", alternatives=alts)
        window_days = task.options.get("window_days")
        if isinstance(window_days, int) and window_days > 0:
            start = date.today()
            end = start + timedelta(days=window_days - 1)
        else:
            start, end = date_window(task.query)
        out = await events_service.search(
            lat=place.lat, lon=place.lon, city=place.city or place.name,
            country_code=place.country_code, country=place.country, category="tech",
            date_from=start.isoformat(), date_to=end.isoformat(), region=place.region,
        )
        events: List[Dict[str, Any]] = out.get("events") or []
        today = date.today().isoformat()

        def order(e: Dict[str, Any]):
            # Same-city first, then the rest of the country; within each,
            # upcoming by date, with long-running already-open ones last.
            ongoing = (e.get("start_date") or "") < today
            return (0 if e.get("locality") in (None, "city") else 1, ongoing,
                    e.get("start_date") or "", e.get("start_time") or "")

        local = sorted((e for e in events if e.get("locality") in (None, "city", "country")
                        and not e.get("online")), key=order)
        remote = [e for e in events if e not in local]
        data = {
            "results": local[:24],
            "online": remote[:12],
            "window": {"from": start.isoformat(), "to": end.isoformat()},
        }
        sources = out.get("sources") or []
        if local:
            return self.result("ok", data=data, sources=sources)
        msg, alts = messages.empty("tech", place.label())
        if remote:
            msg = (f"No in-person tech events are listed in {place.label()} for these dates, "
                   f"but there are {len(remote)} you can join online.")
            return self.result("partial", data=data, message=msg, alternatives=alts[1:], sources=sources)
        return self.result("empty", data=data, message=msg, alternatives=alts, sources=sources)


LOCATION = LocationAgent()
TECH_COMMUNITY = TechCommunityAgent()
