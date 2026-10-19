"""
Positive, actionable copy for when an agent has little or nothing to show.

Rule of thumb: say what isn't available, then immediately what the user
can do instead. Never "No results." / "Error." / provider names.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# domain → (empty message template, alternatives)
_EMPTY: Dict[str, Tuple[str, List[str]]] = {
    "explore": (
        "We couldn't find listings for that near {place} just yet.",
        ["Try a nearby neighborhood or a broader search like “things to do”.",
         "Check the Events page for what's on this week."],
    ),
    "work": (
        "No work-friendly spots are listed near {place} right now.",
        ["Cafés and public libraries are usually good fallbacks.",
         "Try searching a nearby town center."],
    ),
    "events": (
        "Nothing ticketed is listed near {place} for those dates.",
        ["Widen the date range on the Events page.",
         "Local venues, tourist offices and community boards often list more."],
    ),
    "tech": (
        "No tech meetups or hackathons are listed in {place} for these dates.",
        ["Online hackathons and conferences are open to join from anywhere.",
         "A nearby larger city may have more; try searching it on the Events page."],
    ),
    "neighborhoods": (
        "We don't have neighborhood details for {place} yet.",
        ["Search a specific area name to see what's nearby.",
         "Ask about commute times from areas you're considering."],
    ),
    "commute": (
        "We couldn't estimate that trip yet.",
        ["Name both places, like “from the airport to the old town”.",
         "Pick exact addresses on the Commute page for precise times."],
    ),
    "plan": (
        "Your move plan for {place} is still being put together.",
        ["Open Essentials for the most important first steps."],
    ),
    "checklist": (
        "Your essentials for {place} are still being put together.",
        ["The general checklist (address, banking, healthcare) applies anywhere."],
    ),
}

_UNAVAILABLE = "This part of Navis is taking a short break. The rest of your answer is ready below."


def empty(domain: str, place: Optional[str]) -> Tuple[str, List[str]]:
    template, alternatives = _EMPTY.get(
        domain, ("Nothing to show for {place} on this one yet.", ["Try rephrasing or a nearby place."]))
    return template.format(place=place or "this area"), list(alternatives)


def unavailable(domain: str) -> Tuple[str, List[str]]:
    _, alternatives = _EMPTY.get(domain, ("", []))
    return _UNAVAILABLE, alternatives[:1]
