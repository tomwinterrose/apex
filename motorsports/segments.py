"""Racing session segment handling.

Computes per-session start/end windows for race weekends. Each session
(Practice 1, Qualifying, Race, ...) has a fixed duration based on its type,
with the race duration resolved from the event name (endurance races encode
their duration: "24 Hours of Le Mans"), a per-league fallback, or a
configurable default.
"""

import re
from datetime import timedelta

from .types import RacingEvent, RacingSession, SessionWindow

SESSION_ORDER = [
    "fp1",
    "fp2",
    "fp3",
    "sprint_qualifying",
    "sprint",
    "qualifying",
    "race",
]

# Fixed durations (hours) for non-race sessions.
SESSION_DURATION_HOURS: dict[str, float] = {
    "fp1": 1.0,
    "fp2": 1.0,
    "fp3": 1.0,
    "sprint_qualifying": 1.0,
    "sprint": 1.0,
    "qualifying": 1.0,
}

# Per-league fallback race durations for endurance series (hours).
LEAGUE_RACE_DURATION_HOURS: dict[str, float] = {
    "wec": 6.0,
    "imsa": 2.75,
}

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "twenty-four": 24, "twenty four": 24,
}

_DURATION_NAME_RE = re.compile(
    r"\b(\d{1,2}|" + "|".join(_WORD_NUMBERS) + r")\s+hours?\b",
    re.IGNORECASE,
)


def _parse_duration_from_name(name: str | None) -> float | None:
    """Extract race duration (hours) from event name.

    Handles "24 Hours of Le Mans", "6 Hours of Spa", "Twelve Hours of Sebring".
    """
    if not name:
        return None
    match = _DURATION_NAME_RE.search(name)
    if not match:
        return None
    token = match.group(1).lower()
    if token in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[token])
    return float(token)


def _session_duration_hours(
    session_code: str,
    league: str | None = None,
    event_name: str | None = None,
    default_race_hours: float = 3.0,
) -> float:
    """Return the duration (hours) for a session.

    For the race session resolves in order: explicit name duration, per-league
    fallback, then the supplied default.
    """
    if session_code == "race":
        if (d := _parse_duration_from_name(event_name)) is not None:
            return d
        if league and league in LEAGUE_RACE_DURATION_HOURS:
            return LEAGUE_RACE_DURATION_HOURS[league]
        return default_race_hours
    return SESSION_DURATION_HOURS.get(session_code, 1.0)


def expand_sessions(
    event: RacingEvent,
    default_race_hours: float = 3.0,
) -> list[SessionWindow]:
    """Compute start/end windows for every session in a race weekend.

    Args:
        event: Racing event with session data.
        default_race_hours: Fallback race duration when no other hint is available.

    Returns:
        List of SessionWindow objects ordered by start time.
    """
    sessions = sorted(event.sessions, key=lambda s: s.start_time)
    windows: list[SessionWindow] = []

    for session in sessions:
        duration = _session_duration_hours(
            session.code,
            league=event.league,
            event_name=event.name,
            default_race_hours=default_race_hours,
        )
        windows.append(
            SessionWindow(
                code=session.code,
                name=session.name,
                start=session.start_time,
                end=session.start_time + timedelta(hours=duration),
            )
        )

    return windows
