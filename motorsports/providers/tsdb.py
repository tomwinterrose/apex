"""TheSportsDB racing data provider.

TSDB models a motorsport race weekend as several flat per-session events
(Free Practice 1, Qualifying, Race, ...) sharing a season/round.  This
provider fetches all session events via eventsseason.php and groups them back
into multi-session RacingEvent objects.

Supported leagues:
    wec   → TSDB league ID 4413 (FIA World Endurance Championship) — premium
    imsa  → TSDB league ID 4488 (IMSA WeatherTech SportsCar Championship) — free

Rate limits (TSDB):
    Free tier:    30 requests/minute
    Premium tier: 100 requests/minute

Set TSDB_API_KEY to your key (or "1"/"2" for the free public key).
Set TSDB_PREMIUM=1 if you have a premium key.
"""

import logging
import re
import threading
import time
from collections import deque
from datetime import UTC, date, datetime

import httpx

from ..types import RacingEvent, RacingSession

logger = logging.getLogger(__name__)

TSDB_BASE = "https://www.thesportsdb.com/api/v1/json"

TSDB_LEAGUE_MAP: dict[str, str] = {
    "wec": "4413",
    "imsa": "4488",
}

_SESSION_KEYWORDS_RE = re.compile(
    r"practice|qualifying|hyperpole|warm|prologue|fp\d|session", re.IGNORECASE
)
_FREE_PRACTICE_RE = re.compile(r"^(?:free practice|fp)\s*(\d+)$", re.IGNORECASE)
_WARMUP_RE = re.compile(r"^warm[\s-]?up$", re.IGNORECASE)
_QUALIFYING_RE = re.compile(r"^(?:hyperpole\s+)?qualifying(?:\s*[-–]\s*(.+))?$", re.IGNORECASE)
_HYPERPOLE_RE = re.compile(r"^hyperpole\s*(\d*)\s*(?:[-–]\s*(.+))?$", re.IGNORECASE)
_PROLOGUE_RE = re.compile(r"prologue", re.IGNORECASE)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _parse_session_label(event_name: str, race_name: str | None) -> tuple[str, str]:
    if race_name and event_name == race_name:
        return "race", "Race"

    label = event_name
    if race_name and event_name.startswith(race_name):
        label = event_name[len(race_name):].strip()

    if m := _FREE_PRACTICE_RE.match(label):
        num = m.group(1)
        return f"fp{num}", f"Practice {num}"
    if _WARMUP_RE.match(label):
        return "warmup", "Warm Up"
    if m := _QUALIFYING_RE.match(label):
        cls = (m.group(1) or "").strip()
        return (f"qualifying_{_slugify(cls)}", f"Qualifying - {cls}") if cls else ("qualifying", "Qualifying")
    if m := _HYPERPOLE_RE.match(label):
        num = m.group(1) or ""
        cls = (m.group(2) or "").strip()
        code = f"hyperpole{'_' + num if num else ''}{'_' + _slugify(cls) if cls else ''}"
        name = f"Hyperpole{' ' + num if num else ''}{' - ' + cls if cls else ''}"
        return code, name
    if _PROLOGUE_RE.search(label):
        if "afternoon" in label.lower():
            return "prologue_pm", "Prologue (PM)"
        if "morning" in label.lower():
            return "prologue_am", "Prologue (AM)"

    slug = _slugify(label) or "race"
    return slug, label.title()


def _parse_datetime_tsdb(date_str: str | None, time_str: str | None, ts: str | None) -> datetime | None:
    if ts:
        try:
            s = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            pass
    if date_str:
        try:
            combined = f"{date_str}T{time_str}" if time_str else date_str
            dt = datetime.fromisoformat(combined)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            pass
    return None


def _is_race(event_name: str) -> bool:
    return not _SESSION_KEYWORDS_RE.search(event_name)


def _group_into_event(
    group: list[dict], season: str, round_: str, league: str, provider: str
) -> RacingEvent | None:
    ordered = sorted(
        group,
        key=lambda e: _parse_datetime_tsdb(
            e.get("dateEvent"), e.get("strTime"), e.get("strTimestamp")
        ) or datetime.min.replace(tzinfo=UTC),
    )
    race_event = next((e for e in ordered if _is_race(e.get("strEvent", ""))), None)
    race_name = race_event.get("strEvent") if race_event else None
    primary = race_event or ordered[-1]

    sessions: list[RacingSession] = []
    for ev in ordered:
        start = _parse_datetime_tsdb(ev.get("dateEvent"), ev.get("strTime"), ev.get("strTimestamp"))
        if not start:
            continue
        code, name = _parse_session_label(ev.get("strEvent", ""), race_name)
        sessions.append(RacingSession(code=code, name=name, start_time=start))

    if not sessions:
        return None

    sessions.sort(key=lambda s: s.start_time)
    venue_name = primary.get("strVenue") or ""
    circuit = venue_name or None
    event_name = primary.get("strEvent", "")

    return RacingEvent(
        id=f"tsdb_{league}_{season}_{round_}",
        provider=provider,
        name=event_name,
        short_name=event_name,
        start_time=sessions[0].start_time,
        league=league,
        circuit_name=circuit,
        sessions=sessions,
    )


def _parse_season_events(raw: list[dict], league: str, provider: str) -> list[RacingEvent]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for ev in raw:
        season = str(ev.get("strSeason") or "")
        round_ = str(ev.get("intRound") or "")
        groups.setdefault((season, round_), []).append(ev)

    result = []
    for (season, round_), group in groups.items():
        event = _group_into_event(group, season, round_, league, provider)
        if event:
            result.append(event)

    result.sort(key=lambda e: e.start_time)
    return result


class _RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_per_minute: int):
        self._max = max_per_minute
        self._window = 60.0
        self._requests: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            cutoff = now - self._window
            while self._requests and self._requests[0] < cutoff:
                self._requests.popleft()
            if len(self._requests) >= self._max:
                wait = self._window - (now - self._requests[0])
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
                    cutoff = now - self._window
                    while self._requests and self._requests[0] < cutoff:
                        self._requests.popleft()
            self._requests.append(time.monotonic())


class TSDBRacingProvider:
    """Fetches racing events from TheSportsDB."""

    PROVIDER = "tsdb"

    def __init__(self, api_key: str = "1", is_premium: bool = False, timeout: float = 15.0):
        self._api_key = api_key or "1"
        self._is_premium = is_premium
        self._rate_limiter = _RateLimiter(100 if is_premium else 30)
        self._client = httpx.Client(timeout=timeout)
        # Season cache: league → list[RacingEvent]
        self._season_cache: dict[str, list[RacingEvent]] = {}

    def supports(self, league: str) -> bool:
        return league in TSDB_LEAGUE_MAP

    def get_events(self, league: str, target_date: date) -> list[RacingEvent]:
        """Return events for a league where any session falls on target_date."""
        all_events = self._get_season_events(league)
        return [
            e for e in all_events
            if any(s.start_time.date() == target_date for s in e.sessions)
        ]

    def _get_season_events(self, league: str) -> list[RacingEvent]:
        if league in self._season_cache:
            return self._season_cache[league]

        tsdb_id = TSDB_LEAGUE_MAP.get(league)
        if not tsdb_id:
            return []

        today = date.today()
        seasons = [str(today.year)]
        if today.month >= 10:
            seasons.append(str(today.year + 1))

        raw: list[dict] = []
        for season in seasons:
            data = self._fetch("eventsseason.php", {"id": tsdb_id, "s": season})
            if data and data.get("events"):
                raw.extend(data["events"])

        events = _parse_season_events(raw, league, self.PROVIDER)
        self._season_cache[league] = events
        return events

    def _fetch(self, endpoint: str, params: dict) -> dict | None:
        self._rate_limiter.acquire()
        url = f"{TSDB_BASE}/{self._api_key}/{endpoint}"
        try:
            response = self._client.get(url, params=params)
            if response.status_code == 429:
                logger.warning("[TSDB] rate limited, backing off 30s")
                time.sleep(30.0)
                return self._fetch(endpoint, params)
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("[TSDB] request failed for %s", endpoint, exc_info=True)
            return None

    def close(self) -> None:
        self._client.close()
