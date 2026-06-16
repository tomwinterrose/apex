"""Static calendar provider for racing leagues with no live API coverage.

Reads a hand-maintained JSON calendar (calendars/racing_calendars.json) and
serves it as RacingEvent objects. Useful as a fallback when TSDB is unavailable
or as the sole source for series not in ESPN or TSDB.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

from ..types import RacingEvent, RacingSession

logger = logging.getLogger(__name__)

_DEFAULT_CALENDAR = Path(__file__).parent / "calendars" / "racing_calendars.json"


class StaticCalendarProvider:
    """Racing provider backed by a hand-maintained JSON calendar."""

    PROVIDER = "static"

    def __init__(self, data_path: Path | None = None):
        self._data_path = data_path or _DEFAULT_CALENDAR
        self._events: dict[str, list[RacingEvent]] = {}
        self._load()

    def supports(self, league: str) -> bool:
        return league in self._events

    def get_events(self, league: str, target_date: date) -> list[RacingEvent]:
        events = self._events.get(league, [])
        return [
            e for e in events
            if any(s.start_time.date() == target_date for s in e.sessions)
        ]

    def _load(self) -> None:
        try:
            with open(self._data_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("[STATIC] failed to load calendar from %s: %s", self._data_path, e)
            return

        for league, rounds in data.items():
            if league.startswith("_"):
                continue
            events = [e for e in (_parse_round(r, league) for r in rounds) if e]
            events.sort(key=lambda e: e.start_time)
            self._events[league] = events

    def get_supported_leagues(self) -> list[str]:
        return list(self._events.keys())


def _make_abbrev(name: str) -> str:
    words = [w for w in name.split() if len(w) > 2]
    if len(words) >= 2:
        return "".join(w[0].upper() for w in words[:4])
    return name[:6].upper()


def _parse_round(data: dict, league: str) -> RacingEvent | None:
    try:
        event_id = data["id"]
        name = data["name"]
        short_name = data.get("short_name") or name

        sessions: list[RacingSession] = []
        for sd in data.get("sessions", []):
            sessions.append(
                RacingSession(
                    code=sd["code"],
                    name=sd["name"],
                    start_time=datetime.fromisoformat(sd["start_time"]),
                )
            )
        sessions.sort(key=lambda s: s.start_time)
        if not sessions:
            return None

        return RacingEvent(
            id=event_id,
            provider="static",
            name=name,
            short_name=short_name,
            start_time=sessions[0].start_time,
            league=league,
            circuit_name=data.get("circuit_name"),
            sessions=sessions,
        )
    except (KeyError, ValueError) as e:
        logger.warning("[STATIC] failed to parse round %r for %s: %s", data.get("id"), league, e)
        return None
