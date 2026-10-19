"""
Time-aware intelligence for ranking and suggestions.

Uses system clock only — never fabricates temporal data.

Time signals:
  - time_of_day: "morning" | "afternoon" | "evening" | "night"
  - is_now:      bool, true if query contains "now" or "open"
  - is_tonight:  bool, true if query contains "tonight"
  - is_week:     bool, true if query contains "this week"
  - day_type:    "weekday" | "weekend"
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any


class TimeContext:
    def __init__(self, now: datetime = None):
        self.now = now or datetime.now(timezone.utc)
        self.hour = self.now.hour
        self.weekday = self.now.weekday()  # 0=Mon, 6=Sun
        self._query_hints = {}

    @property
    def time_of_day(self) -> str:
        if 5 <= self.hour < 12:
            return "morning"
        if 12 <= self.hour < 17:
            return "afternoon"
        if 17 <= self.hour < 21:
            return "evening"
        return "night"

    @property
    def day_type(self) -> str:
        return "weekend" if self.weekday >= 5 else "weekday"

    @property
    def open_now_boost(self) -> float:
        """Higher boost for open_now during evening/night when closures are common."""
        if self.time_of_day in ("evening", "night"):
            return 4.0
        return 2.0

    @property
    def event_recency_weight(self) -> float:
        """Events happening sooner get higher weight in evening."""
        if self.time_of_day == "evening":
            return 3.0
        return 1.0

    @classmethod
    def from_query(cls, query: str) -> "TimeContext":
        """Create TimeContext, optionally enriched by query keywords."""
        tc = cls()
        tc._query_hints = {
            "is_now": any(k in query.lower() for k in ["now", "open", "right now"]),
            "is_tonight": "tonight" in query.lower(),
            "is_week": "this week" in query.lower() or "week" in query.lower(),
            "is_urgent": any(k in query.lower() for k in ["urgent", "emergency", "asap"]),
        }
        return tc

    @property
    def is_now(self) -> bool:
        return self._query_hints.get("is_now", False)

    @property
    def is_tonight(self) -> bool:
        return self._query_hints.get("is_tonight", False)

    @property
    def is_week(self) -> bool:
        return self._query_hints.get("is_week", False)

    @property
    def is_urgent(self) -> bool:
        return self._query_hints.get("is_urgent", False)

    def parse_time_context(self, query: str) -> Dict[str, Any]:
        """
        Parse temporal context from query.
        Returns {
            "is_now": bool,
            "is_tonight": bool,
            "is_week": bool,
            "is_urgent": bool,
            "time_of_day": str,
            "day_type": str
        }
        """
        return {
            "is_now": "now" in query.lower() or "open" in query.lower(),
            "is_tonight": "tonight" in query.lower(),
            "is_week": "this week" in query.lower() or "week" in query.lower(),
            "is_urgent": any(k in query.lower() for k in ["urgent", "emergency", "asap"]),
            "time_of_day": self.time_of_day,
            "day_type": self.day_type,
        }

    def is_relevant_time(self, event: Dict[str, Any]) -> bool:
        """
        Check if event start_time matches temporal context.
        Returns True if event is relevant to NOW/TONIGHT/WEEK context.
        """
        start_time_str = event.get("start_time", "")
        if not start_time_str:
            return True  # If no time, assume relevant

        try:
            # Try parsing ISO 8601 format
            from dateutil import parser
            event_time = parser.isoparse(start_time_str)
        except Exception:
            # Fallback: assume relevant if we can't parse
            return True

        # If user asked for NOW, event must be within 2 hours
        if self.is_now:
            two_hours_ahead = self.now + timedelta(hours=2)
            return self.now <= event_time <= two_hours_ahead

        # If user asked for TONIGHT, event must be between now and midnight
        if self.is_tonight:
            tonight_end = self.now.replace(hour=23, minute=59, second=59)
            return self.now <= event_time <= tonight_end

        # If user asked for THIS WEEK, event must be within 7 days
        if self.is_week:
            week_end = self.now + timedelta(days=7)
            return self.now <= event_time <= week_end

        # Default: always relevant
        return True

    def urgency_rank(self) -> float:
        """
        Urgency score for services (0.0-2.0).
        Higher during evening/night when urgent services are more needed.
        """
        if self.is_urgent:
            return 2.0
        if self.time_of_day == "night":
            return 1.0
        if self.time_of_day == "evening":
            return 0.5
        return 0.0
