"""Core data types for the motorsports matcher."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RacingResult:
    """A single driver's result for a session."""

    driver_name: str
    team_name: str | None = None
    position: int | None = None
    grid_position: int | None = None
    points: float | None = None
    fastest_lap: bool = False
    status: str | None = None


@dataclass(frozen=True)
class RacingSession:
    """One session within a race weekend (Practice, Qualifying, Race, ...)."""

    code: str  # "fp1", "fp2", "fp3", "sprint_qualifying", "sprint", "qualifying", "race"
    name: str  # "Practice 1", "Qualifying", "Race"
    start_time: datetime
    results: list[RacingResult] = field(default_factory=list)


@dataclass
class RacingEvent:
    """A racing event (Grand Prix, race weekend)."""

    id: str
    provider: str
    name: str
    short_name: str
    start_time: datetime
    league: str
    circuit_name: str | None = None
    sessions: list[RacingSession] = field(default_factory=list)


@dataclass
class SessionWindow:
    """A session with its computed start/end window."""

    code: str
    name: str
    start: datetime
    end: datetime


@dataclass
class MatchResult:
    """Result of matching a stream name to a racing event."""

    matched: bool
    method: str | None = None  # "direct", "fuzzy"
    confidence: float = 0.0
    event: RacingEvent | None = None
    sessions: list[SessionWindow] = field(default_factory=list)
    reason: str | None = None
