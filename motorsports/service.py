"""Motorsport service: multi-provider orchestration.

Provider precedence per league:
  ESPN-backed  (f1, nascar-cup, nascar-xfinity, nascar-truck, indycar, motogp)
      → ESPNRacingProvider (primary)
  TSDB-backed  (wec, imsa)
      → TSDBRacingProvider (primary, requires TSDB_API_KEY)
      → StaticCalendarProvider (fallback when TSDB is unavailable)
"""

import logging
import os
from datetime import date

from .matcher import match_stream
from .providers.espn import ESPN_LEAGUE_MAP, ESPNRacingProvider
from .providers.static import StaticCalendarProvider
from .providers.tsdb import TSDB_LEAGUE_MAP, TSDBRacingProvider
from .types import MatchResult, RacingEvent

logger = logging.getLogger(__name__)

# Human-readable league metadata for the /leagues endpoint.
LEAGUE_META: dict[str, dict] = {
    "f1": {"name": "Formula 1", "series": "F1", "provider": "espn"},
    "nascar-cup": {"name": "NASCAR Cup Series", "series": "NASCAR", "provider": "espn"},
    "nascar-xfinity": {"name": "NASCAR Xfinity Series", "series": "NASCAR", "provider": "espn"},
    "nascar-truck": {"name": "NASCAR Craftsman Truck Series", "series": "NASCAR", "provider": "espn"},
    "indycar": {"name": "IndyCar Series", "series": "IndyCar", "provider": "espn"},
    "motogp": {"name": "MotoGP", "series": "MotoGP", "provider": "espn"},
    "wec": {"name": "FIA World Endurance Championship", "series": "WEC", "provider": "tsdb"},
    "imsa": {"name": "IMSA WeatherTech SportsCar Championship", "series": "IMSA", "provider": "tsdb"},
}


class MotorsportService:
    """Orchestrates provider access and exposes a clean API."""

    def __init__(
        self,
        tsdb_api_key: str | None = None,
        tsdb_premium: bool = False,
        default_race_hours: float = 3.0,
    ):
        self._espn = ESPNRacingProvider()
        tsdb_key = tsdb_api_key or os.environ.get("TSDB_API_KEY") or "1"
        tsdb_prem = tsdb_premium or bool(os.environ.get("TSDB_PREMIUM"))
        self._tsdb = TSDBRacingProvider(api_key=tsdb_key, is_premium=tsdb_prem)
        self._static = StaticCalendarProvider()
        self._default_race_hours = default_race_hours

    def get_leagues(self) -> list[dict]:
        """Return metadata for all supported leagues."""
        leagues = []
        for code, meta in LEAGUE_META.items():
            entry = {"code": code, **meta}
            # Flag TSDB leagues that need a key to work properly
            if meta["provider"] == "tsdb":
                entry["note"] = "requires TSDB_API_KEY; falls back to static calendar"
            leagues.append(entry)
        return leagues

    def get_events(self, league: str, target_date: date) -> list[RacingEvent]:
        """Fetch racing events for a league on a given date."""
        if league in ESPN_LEAGUE_MAP:
            return self._espn.get_events(league, target_date)

        if league in TSDB_LEAGUE_MAP:
            events = self._tsdb.get_events(league, target_date)
            if not events and self._static.supports(league):
                logger.info("[SERVICE] TSDB returned no events for %s, trying static calendar", league)
                events = self._static.get_events(league, target_date)
            return events

        if self._static.supports(league):
            return self._static.get_events(league, target_date)

        logger.warning("[SERVICE] unsupported league: %s", league)
        return []

    def match(
        self,
        stream_name: str,
        league: str,
        target_date: date,
    ) -> MatchResult:
        """Match a stream name to a racing event, returning sessions on success."""
        events = self.get_events(league, target_date)
        return match_stream(
            stream_name,
            events,
            target_date,
            default_race_hours=self._default_race_hours,
        )

    def close(self) -> None:
        self._espn.close()
        self._tsdb.close()
