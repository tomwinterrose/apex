"""ESPN racing data provider.

Fetches race-weekend events from ESPN's public scoreboard API and normalises
them into RacingEvent objects with per-session detail.

Supported leagues and their ESPN sport/league paths:
    f1              → racing/f1
    nascar-cup      → racing/nascar-premier
    nascar-xfinity  → racing/nascar-secondary
    nascar-truck    → racing/nascar-truck
    indycar         → racing/irl
    motogp          → racing/motogp
"""

import logging
import time
from datetime import UTC, date, datetime

import httpx

from ..types import RacingEvent, RacingResult, RacingSession

logger = logging.getLogger(__name__)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Maps our league code to ESPN's {sport}/{league} URL segment.
ESPN_LEAGUE_MAP: dict[str, str] = {
    "f1": "racing/f1",
    "nascar-cup": "racing/nascar-premier",
    "nascar-xfinity": "racing/nascar-secondary",
    "nascar-truck": "racing/nascar-truck",
    "indycar": "racing/irl",
    "motogp": "racing/motogp",
}

# Maps ESPN competition type abbreviations to our canonical session codes.
_SESSION_ABBREV: dict[str, str] = {
    "fp1": "fp1", "p1": "fp1",
    "fp2": "fp2", "p2": "fp2",
    "fp3": "fp3", "p3": "fp3",
    "sq": "sprint_qualifying",
    "sprint qualifying": "sprint_qualifying",
    "sprint": "sprint",
    "qual": "qualifying",
    "qualifying": "qualifying",
    "race": "race",
}

_SESSION_NAMES: dict[str, str] = {
    "fp1": "Practice 1",
    "fp2": "Practice 2",
    "fp3": "Practice 3",
    "sprint_qualifying": "Sprint Qualifying",
    "sprint": "Sprint",
    "qualifying": "Qualifying",
    "race": "Race",
}


def _session_info(type_data: dict | None) -> tuple[str, str]:
    abbrev = (type_data or {}).get("abbreviation", "").strip().lower()
    code = _SESSION_ABBREV.get(abbrev, "race")
    name = _SESSION_NAMES.get(code, code.replace("_", " ").title())
    return code, name


def _parse_datetime(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _make_abbrev(name: str) -> str:
    words = [w for w in name.split() if len(w) > 2]
    if len(words) >= 2:
        return "".join(w[0].upper() for w in words[:4])
    return name[:6].upper()


def _parse_racing_session(competition: dict) -> RacingSession | None:
    start_time = _parse_datetime(competition.get("date"))
    if not start_time:
        return None

    code, name = _session_info(competition.get("type"))
    comp_state = competition.get("status", {}).get("type", {}).get("state", "pre")

    results: list[RacingResult] = []
    for competitor in competition.get("competitors", []):
        athlete = competitor.get("athlete") or {}
        driver_name = athlete.get("fullName") or athlete.get("displayName")
        if not driver_name:
            continue
        order = competitor.get("order")
        stats = competitor.get("statistics", [])
        points: float | None = None
        fastest_lap = False
        for stat in stats:
            stat_name = (stat.get("name") or "").lower()
            if "points" in stat_name:
                try:
                    points = float(stat.get("value"))
                except (TypeError, ValueError):
                    pass
            if "fastestlap" in stat_name:
                fastest_lap = bool(stat.get("value"))
        results.append(
            RacingResult(
                driver_name=driver_name,
                position=order if comp_state == "post" else None,
                grid_position=order if comp_state != "post" else None,
                points=points,
                fastest_lap=fastest_lap,
                status="Finished" if comp_state == "post" else None,
            )
        )

    return RacingSession(code=code, name=name, start_time=start_time, results=results)


def _parse_racing_event(data: dict, league: str, provider_name: str) -> RacingEvent | None:
    try:
        event_id = data.get("id", "")
        if not event_id:
            return None

        start_time = _parse_datetime(data.get("date"))
        if not start_time:
            return None

        event_name = data.get("name", "")
        short_name = data.get("shortName", event_name)

        circuit_data = data.get("circuit") or {}
        circuit_name = circuit_data.get("fullName")

        competitions = data.get("competitions", [])
        sessions: list[RacingSession] = []
        for competition in competitions:
            session = _parse_racing_session(competition)
            if session:
                sessions.append(session)
        sessions.sort(key=lambda s: s.start_time)

        return RacingEvent(
            id=str(event_id),
            provider=provider_name,
            name=event_name,
            short_name=short_name,
            start_time=start_time,
            league=league,
            circuit_name=circuit_name,
            sessions=sessions,
        )
    except Exception:
        logger.warning("[ESPN] failed to parse event", exc_info=True)
        return None


class ESPNRacingProvider:
    """Fetches racing events from ESPN's public scoreboard API."""

    PROVIDER = "espn"

    def __init__(self, timeout: float = 10.0, retries: int = 3):
        self._client = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self._retries = retries

    def supports(self, league: str) -> bool:
        return league in ESPN_LEAGUE_MAP

    def get_events(self, league: str, target_date: date) -> list[RacingEvent]:
        """Fetch racing events for a league on the given date."""
        sport_league = ESPN_LEAGUE_MAP.get(league)
        if not sport_league:
            return []

        date_str = target_date.strftime("%Y%m%d")
        url = f"{ESPN_BASE}/{sport_league}/scoreboard"
        params = {"dates": date_str}

        data = self._get(url, params)
        if not data:
            return []

        events = []
        for event_data in data.get("events", []):
            event = _parse_racing_event(event_data, league, self.PROVIDER)
            if event:
                events.append(event)

        return events

    def _get(self, url: str, params: dict) -> dict | None:
        for attempt in range(self._retries):
            try:
                response = self._client.get(url, params=params)
                if response.status_code == 429:
                    wait = 5.0 * (attempt + 1)
                    logger.warning("[ESPN] rate limited, waiting %.0fs", wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.warning("[ESPN] HTTP %d for %s", e.response.status_code, url)
                return None
            except Exception:
                if attempt < self._retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning("[ESPN] request failed after %d retries", self._retries, exc_info=True)
        return None

    def close(self) -> None:
        self._client.close()
