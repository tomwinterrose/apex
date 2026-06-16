"""Motorsports stream-to-event matcher.

Matches a stream name (e.g. "F1: Monaco Grand Prix") to a racing event using
two strategies:

1. Direct — if exactly one event's session window covers the target date, match
   it directly (the common case: one Grand Prix per league per weekend). Still
   requires a sanity-threshold fuzzy score so completely unrelated streams don't
   match by elimination.

2. Fuzzy — when multiple events are candidates, fuzzy-match the stream name
   against each event's name, short_name, and circuit_name.
"""

import logging
from datetime import date
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz

from .normalize import normalize_text
from .segments import expand_sessions
from .types import MatchResult, RacingEvent

logger = logging.getLogger(__name__)

# Minimum score (0-100) for a fuzzy match when multiple events are candidates.
RACING_MATCH_THRESHOLD = 70

# Minimum score for the "single event covers the date" shortcut, to avoid
# matching cycling/talk-show streams to the only race happening that weekend.
SINGLE_EVENT_SANITY_THRESHOLD = 50


def _covers_date(event: RacingEvent, target_date: date, tz: ZoneInfo) -> bool:
    """True if any session in the event's weekend falls on target_date."""
    for session in event.sessions:
        if session.start_time.astimezone(tz).date() == target_date:
            return True
    return False


def match_stream(
    stream_name: str,
    events: list[RacingEvent],
    target_date: date,
    user_tz: ZoneInfo | None = None,
    default_race_hours: float = 3.0,
) -> MatchResult:
    """Match a stream name to a racing event.

    Args:
        stream_name: Raw stream name to match (e.g. "F1: Monaco Grand Prix").
        events: Candidate events fetched for the league (any date range is fine;
                this function filters to those covering target_date).
        target_date: The date the stream is airing.
        user_tz: Timezone for date comparison (defaults to UTC).
        default_race_hours: Fallback race duration when no other hint is found.

    Returns:
        MatchResult with matched=True and session windows on success.
    """
    tz = user_tz or ZoneInfo("UTC")
    covering = [e for e in events if _covers_date(e, target_date, tz)]

    if not covering:
        logger.debug("[MATCH] no events covering %s for %d candidates", target_date, len(events))
        return MatchResult(matched=False, reason="no_events_for_date")

    stream_norm = normalize_text(stream_name)
    best_score = 0
    best_event: RacingEvent | None = None

    for event in covering:
        for candidate in (event.name, event.short_name, event.circuit_name):
            if not candidate:
                continue
            score = fuzz.token_set_ratio(stream_norm, normalize_text(candidate))
            if score > best_score:
                best_score = score
                best_event = event

    # Strategy 1: single event covering the date (common case — one GP per weekend)
    if len(covering) == 1 and best_score >= SINGLE_EVENT_SANITY_THRESHOLD:
        event = covering[0]
        logger.debug(
            "[MATCH] direct: stream=%r -> %r (score=%d)", stream_name[:50], event.name, best_score
        )
        return MatchResult(
            matched=True,
            method="direct",
            confidence=1.0,
            event=event,
            sessions=expand_sessions(event, default_race_hours),
        )

    # Strategy 2: fuzzy match across multiple candidates
    if best_event and best_score >= RACING_MATCH_THRESHOLD:
        logger.debug(
            "[MATCH] fuzzy: stream=%r -> %r (score=%d)", stream_name[:50], best_event.name, best_score
        )
        return MatchResult(
            matched=True,
            method="fuzzy",
            confidence=best_score / 100.0,
            event=best_event,
            sessions=expand_sessions(best_event, default_race_hours),
        )

    logger.debug(
        "[MATCH] failed: stream=%r, best_score=%d, %d covering events",
        stream_name[:50], best_score, len(covering),
    )
    return MatchResult(
        matched=False,
        reason=f"score_too_low ({best_score} < {RACING_MATCH_THRESHOLD} for {len(covering)} events)",
    )
