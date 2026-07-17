"""Racing pipeline tests: classification, matcher scoring, session durations.

Racing leagues are configured with ``event_type='event'`` and have no reliable
text keyword, so a stream is classified ``RACING_EVENT`` purely because the
group is racing-dominant and the stream has no team pattern. This is the
regression-prone path (cf. #157): a team-sport stream that leaks into a
racing-dominant group must NOT be hijacked as a race.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from apex.consumers.matching.classifier import (
    StreamCategory,
    classify_stream,
    detect_racing_series_leagues,
)
from apex.consumers.matching.racing_matcher import RacingMatchContext, RacingMatcher
from apex.consumers.racing_segments import (
    _is_practice_session,
    _isolate_stream_session_label,
    _parse_duration_from_name,
    _session_category_from_stream_name,
    _session_duration_hours,
    _session_in_category,
    expand_racing_segments,
    nearest_session,
)
from apex.services.detection_keywords import DetectionKeywordService


def setup_function():
    DetectionKeywordService.invalidate_cache()


# ---------------------------------------------------------------------------
# Classification: genuine racing streams classify as RACING_EVENT
# ---------------------------------------------------------------------------


def test_f1_stream_classifies_racing():
    c = classify_stream("F1: Monaco Grand Prix", league_event_type="event")
    assert c.category == StreamCategory.RACING_EVENT
    assert c.event_hint  # full text carried for fuzzy matching


def test_nascar_stream_classifies_racing():
    c = classify_stream("NASCAR Cup Series - Daytona 500", league_event_type="event")
    assert c.category == StreamCategory.RACING_EVENT


def test_nascar_espn_at_city_format_classifies_racing():
    # ESPN names NASCAR events "[Series] at [City]" — the "at" must not trigger
    # team extraction since "NASCAR Cup Series" is a series name, not a team abbrev.
    c = classify_stream("NASCAR Cup Series at San Diego", league_event_type="event")
    assert c.category == StreamCategory.RACING_EVENT


def test_nascar_orap_at_city_format_classifies_racing():
    c = classify_stream("NASCAR O'Reilly Auto Parts Series at San Diego", league_event_type="event")
    assert c.category == StreamCategory.RACING_EVENT


def test_racing_only_applies_for_event_league_type():
    # Same name, but a non-racing (team) group must not route to racing.
    c = classify_stream("F1: Monaco Grand Prix", league_event_type="team")
    assert c.category != StreamCategory.RACING_EVENT


# ---------------------------------------------------------------------------
# Classification: leaked team-sport streams in a racing-dominant group are
# NOT hijacked
# ---------------------------------------------------------------------------


def test_team_stream_with_separator_falls_through():
    # "SD at BAL" has a game separator → team matching, not racing.
    c = classify_stream("SD at BAL", league_event_type="event")
    assert c.category == StreamCategory.TEAM_VS_TEAM


def test_team_stream_with_nonracing_sport_hint_falls_through():
    # No separator, but a positive non-racing sport hint ("Ice Hockey") vetoes
    # racing classification — the #242 follow-up guard.
    c = classify_stream("NHL | Ice Hockey: Maple Leafs", league_event_type="event")
    assert c.category != StreamCategory.RACING_EVENT


def test_hockey_single_team_in_racing_group_is_not_racing():
    c = classify_stream("US | Ice Hockey: Maple Leafs", league_event_type="event")
    assert c.category != StreamCategory.RACING_EVENT


def test_racing_league_hints_cover_all_schema_racing_leagues():
    """_RACING_LEAGUE_HINTS is a hardcoded mirror of the racing leagues seeded in
    schema.sql (the classifier is a pure text module with no DB access). This test
    is the sync contract: add a racing league to the schema and it fails until the
    frozenset learns the new code."""
    import re
    from pathlib import Path

    from apex.consumers.matching.classifier import _RACING_LEAGUE_HINTS

    schema = Path("apex/database/schema.sql").read_text(encoding="utf-8")
    schema_racing_codes = {
        m.group(1)
        for m in re.finditer(r"^\s*\('([a-z0-9-]+)',[^)\n]*'racing'", schema, re.MULTILINE)
    }
    assert schema_racing_codes, "failed to parse racing leagues from schema.sql"
    missing = schema_racing_codes - _RACING_LEAGUE_HINTS
    assert not missing, f"racing leagues in schema.sql missing from _RACING_LEAGUE_HINTS: {missing}"


# ---------------------------------------------------------------------------
# RacingMatcher venue-country scoring (take-and-fix of PR #263)
#
# venue.country is deliberately NOT a peer fuzzy candidate: token_set_ratio
# scores a bare country subset at 100, so a country hit must never outrank a
# real name/circuit match on a different event. It contributes only:
# - to the single-covering-event sanity check (no ambiguity to create), and
# - as a fallback when it identifies exactly ONE covering event.
# ---------------------------------------------------------------------------


def _event(eid, name, circuit=None, country=None):
    return SimpleNamespace(
        id=eid,
        name=name,
        short_name=name,
        circuit_name=circuit,
        venue=SimpleNamespace(country=country) if country else None,
        league="nascar-cup",
    )


def _ctx(stream_name):
    return RacingMatchContext(
        stream_name=stream_name,
        stream_id=1,
        group_id=1,
        target_date=date(2026, 6, 14),
        generation=1,
        user_tz=ZoneInfo("UTC"),
        classified=None,
    )


def _matcher():
    return RacingMatcher(service=None, cache=None)


def test_name_match_beats_country_on_other_event():
    # Doubleheader window: the stream names race A; race B shares no name tokens
    # but its venue country appears in the stream. A must win.
    a = _event("a", "Viva Mexico 250", circuit="Autodromo Hermanos Rodriguez", country="Mexico")
    b = _event("b", "Firekeepers Casino 400", circuit="Michigan Intl Speedway", country="USA")
    out = _matcher()._match_to_event(_ctx("NASCAR Cup: Viva Mexico 250"), [a, b], "nascar-cup")
    assert out.is_matched and out.event.id == "a"


def test_unique_country_fallback_matches():
    # "at Mexico City" carries no event-name tokens, but only one covering
    # event is in Mexico → country fallback resolves it.
    a = _event("a", "Viva Mexico 250", country="Mexico")
    b = _event("b", "Firekeepers Casino 400", country="USA")
    out = _matcher()._match_to_event(
        _ctx("NASCAR Cup Series at Mexico"), [a, b], "nascar-cup"
    )
    assert out.is_matched and out.event.id == "a"


def test_ambiguous_country_does_not_match():
    # Two covering events in the same country: a bare country reference must
    # stay unmatched rather than guess.
    a = _event("a", "Race One GP", country="USA")
    b = _event("b", "Race Two GP", country="USA")
    out = _matcher()._match_to_event(_ctx("Cup Series live from USA"), [a, b], "nascar-cup")
    assert not out.is_matched


def test_single_event_country_passes_sanity_check():
    # One covering event whose name shares nothing with the stream, but the
    # stream names the venue country → sanity check passes via country score.
    a = _event("a", "Viva 250", country="Mexico")
    out = _matcher()._match_to_event(_ctx("NASCAR at Mexico"), [a], "nascar-cup")
    assert out.is_matched and out.event.id == "a"


def test_single_event_generic_venue_word_alone_does_not_match():
    # Live false positive: an unrelated motorcycle "FIM Speedway GP" stream
    # scored 53 (>= SINGLE_EVENT_SANITY_THRESHOLD) against NASCAR's
    # "Atlanta Motor Speedway" purely on the shared generic word "Speedway"
    # — zero real connection to NASCAR or this event. A bare score clearing
    # the sanity threshold must not be enough without actual text evidence
    # the stream names the right racing series.
    a = _event("a", "Focused Health 250", circuit="Atlanta Motor Speedway")
    out = _matcher()._match_to_event(
        _ctx("HBO UK 047 | Malilla - FIM Speedway GP | Round 6 | Malilla"),
        [a], "nascar-xfinity",
    )
    assert not out.is_matched


def test_single_event_matches_with_text_evidence_even_at_sanity_threshold():
    # Positive counterpart: a real NASCAR stream must still match via
    # Strategy 1 when it clears the sanity threshold AND names the series.
    a = _event("a", "Focused Health 250", circuit="Atlanta Motor Speedway")
    out = _matcher()._match_to_event(
        _ctx("NASCAR ORAP Series: Focused Health 250"), [a], "nascar-xfinity"
    )
    assert out.is_matched and out.event.id == "a"


# ---------------------------------------------------------------------------
# RacingMatcher anchor-time gating (EPG path) — follow-up to apexv2-w42k
#
# The EPG text-evidence gate (has_racing_text_evidence in classifier.py) only
# proves a programme NAMES a racing series — it says nothing about whether the
# programme is actually airing that series right now. A filler/stub EPG
# programme (e.g. "Coming up: WEC Racing starting Friday at 9:00 AM",
# duplicated verbatim across unrelated channels with no real listings behind
# them) passes that gate yet has no real broadcast tied to it. _covers_instant
# closes that gap by requiring a session to actually be airing (within
# tolerance) at the programme's own broadcast instant, not just somewhere in
# the race weekend's calendar span.
# ---------------------------------------------------------------------------


def _racing_session(code, start_time):
    return SimpleNamespace(code=code, start_time=start_time)


def _wec_event_with_sessions(sessions):
    return SimpleNamespace(
        id="tsdb_wec_2026_4",
        name="6 Hours of São Paulo",
        short_name="6 Hours of São Paulo",
        circuit_name="Autódromo José Carlos Pace",
        venue=SimpleNamespace(country="Brazil"),
        league="wec",
        sessions=sessions,
        start_time=sessions[0].start_time,
    )


def test_covers_instant_true_near_a_real_session():
    race_start = datetime(2026, 7, 12, 14, 0, tzinfo=UTC)
    event = _wec_event_with_sessions([_racing_session("race", race_start)])
    matcher = _matcher()
    assert matcher._covers_instant(event, race_start, None)
    assert matcher._covers_instant(event, race_start - timedelta(minutes=30), None)


def test_covers_instant_false_for_filler_programme_hours_away():
    # Reproduces a live false positive: a filler "Coming up: WEC Racing..."
    # programme airing 5+ hours from any real session must not bind to the
    # event just because it shares the calendar date.
    race_start = datetime(2026, 7, 12, 14, 0, tzinfo=UTC)
    event = _wec_event_with_sessions([_racing_session("race", race_start)])
    filler_programme_time = race_start - timedelta(hours=5, minutes=26)
    matcher = _matcher()
    assert not matcher._covers_instant(event, filler_programme_time, None)


def test_covers_instant_checks_every_session_in_the_weekend():
    # A multi-session weekend: an instant near ANY session (not just the
    # first) counts as covered.
    fp1 = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)
    race = datetime(2026, 7, 12, 14, 0, tzinfo=UTC)
    event = _wec_event_with_sessions(
        [_racing_session("fp1", fp1), _racing_session("race", race)]
    )
    matcher = _matcher()
    assert matcher._covers_instant(event, fp1, None)
    assert matcher._covers_instant(event, race, None)
    assert not matcher._covers_instant(event, fp1 + timedelta(hours=6), None)


# ---------------------------------------------------------------------------
# RacingMatcher EPG-path match date: a programme's own broadcast date, not the
# run's target_date, decides which race weekend it can bind to.
#
# EPG programme titles rarely carry an explicit date, so extracted_date is
# None and the matcher used to fall back to the run's target_date. Guides
# publish a race weekend days ahead: on Thursday's runs, Friday's "1st
# Practice" programme was matched against Thursday — no event covers that
# date — and stayed unmatched until the run date reached the weekend. With
# anchor_dt available (EPG path always has it), the programme's own date is
# the right fallback; the anchor gate still enforces session proximity.
# ---------------------------------------------------------------------------


@dataclass
class _FakeRacingEvent:
    """dataclass (not SimpleNamespace) so _cache_result's asdict() works."""

    id: str
    name: str
    short_name: str
    circuit_name: str
    league: str
    sport: str
    start_time: datetime
    sessions: list
    venue: object = None


class _FakeMatchCache:
    def __init__(self):
        self.set_calls = []

    def get(self, *args, **kwargs):
        return None

    def touch(self, *args, **kwargs):
        pass

    def delete(self, *args, **kwargs):
        pass

    def set(self, **kwargs):
        self.set_calls.append(kwargs)


class _FakeSportsService:
    def __init__(self, events):
        self._events = events
        self.requested_dates = []

    def get_provider_name(self, league):
        return "espn"

    def get_events(self, league, target_date, cache_only=False):
        self.requested_dates.append(target_date)
        return self._events


def _belgian_gp():
    fp1 = datetime(2026, 7, 17, 11, 30, tzinfo=UTC)
    race = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)
    return _FakeRacingEvent(
        id="espn_f1_belgium_2026",
        name="Belgian Grand Prix",
        short_name="Belgian Grand Prix",
        circuit_name="Circuit de Spa-Francorchamps",
        league="f1",
        sport="racing",
        start_time=fp1,
        sessions=[_racing_session("fp1", fp1), _racing_session("race", race)],
    )


def _match_belgian_gp(anchor_dt):
    event = _belgian_gp()
    service = _FakeSportsService([event])
    matcher = RacingMatcher(service=service, cache=_FakeMatchCache())
    classified = classify_stream(
        "Formula 1 | Belgian Grand Prix: 1st Practice", league_event_type="event"
    )
    assert classified.category == StreamCategory.RACING_EVENT
    assert classified.normalized.extracted_date is None  # premise: no date in text
    outcome = matcher.match(
        classified=classified,
        league="f1",
        target_date=date(2026, 7, 16),  # Thursday's run, weekend starts Friday
        group_id=1,
        stream_id=1,
        generation=1,
        user_tz=ZoneInfo("America/Chicago"),
        anchor_dt=anchor_dt,
    )
    return outcome, service


def test_epg_programme_matches_by_its_own_broadcast_date():
    # Friday 11:00 UTC guide slot, 30 min before FP1 — inside anchor tolerance.
    outcome, service = _match_belgian_gp(anchor_dt=datetime(2026, 7, 17, 11, 0, tzinfo=UTC))
    assert outcome.is_matched and outcome.event.id == "espn_f1_belgium_2026"
    # Events were fetched for the programme's date, not the run's.
    assert service.requested_dates == [date(2026, 7, 17)]


def test_name_path_still_uses_run_target_date():
    # Without an anchor (plain stream-name path) the old fallback holds: the
    # Thursday run date isn't covered by the weekend, so no match yet.
    outcome, service = _match_belgian_gp(anchor_dt=None)
    assert not outcome.is_matched
    assert service.requested_dates == [date(2026, 7, 16)]


# ---------------------------------------------------------------------------
# Racing session duration resolution (apex/consumers/racing_segments.py)
#
# `_parse_duration_from_name` and `_session_duration_hours` for endurance races
# (WEC/IMSA) whose race length varies far more than the global "racing" sport
# default allows.
# ---------------------------------------------------------------------------


class TestParseDurationFromName:
    def test_digit_hours(self):
        assert _parse_duration_from_name("24 Hours of Le Mans") == 24.0
        assert _parse_duration_from_name("6 Hours of Spa-Francorchamps") == 6.0

    def test_word_number_hours(self):
        assert _parse_duration_from_name("Mobil 1 Twelve Hours of Sebring") == 12.0

    def test_no_duration_in_name(self):
        assert _parse_duration_from_name("Rolex 24 At Daytona") is None
        assert _parse_duration_from_name("Petit Le Mans") is None
        assert _parse_duration_from_name("Battle on the Bricks") is None

    def test_none_name(self):
        assert _parse_duration_from_name(None) is None


class TestSessionDurationHours:
    def test_non_race_sessions_unaffected(self):
        assert _session_duration_hours("fp1", {}, "wec", "24 Hours of Le Mans") == 1.0
        assert _session_duration_hours("qualifying", {}, "imsa", "Petit Le Mans") == 1.0

    def test_explicit_name_duration_wins(self):
        assert _session_duration_hours("race", {}, "wec", "24 Hours of Le Mans") == 24.0
        twelve = _session_duration_hours("race", {}, "imsa", "Mobil 1 Twelve Hours of Sebring")
        assert twelve == 12.0

    def test_league_fallback_when_name_has_no_duration(self):
        assert _session_duration_hours("race", {}, "wec", "Petit Le Mans") == 6.0
        assert _session_duration_hours("race", {}, "imsa", "Battle on the Bricks") == 2.75

    def test_sport_default_for_other_leagues(self):
        assert _session_duration_hours("race", {"racing": 3.0}, "f1", "Monaco Grand Prix") == 3.0

    def test_sport_default_when_no_league(self):
        assert _session_duration_hours("race", {"racing": 3.0}) == 3.0


# ---------------------------------------------------------------------------
# expand_racing_segments: scoping to a stream's own named session
#
# A dedicated single-session feed (e.g. "Free Practice 3") must not also be
# offered as the source for the Qualifying/Race channels. A stream whose name
# carries no session hint (a linear channel's own branding) must keep the
# full fan-out — narrowing must never happen without positive evidence, to
# avoid false negatives (a legitimate whole-weekend channel disappearing
# from sessions it should still cover).
# ---------------------------------------------------------------------------


def _wec_sessions():
    base = datetime(2026, 7, 11, 9, tzinfo=UTC)
    return [
        SimpleNamespace(code="fp1", name="Free Practice 1", start_time=base),
        SimpleNamespace(code="fp2", name="Free Practice 2", start_time=base + timedelta(hours=4)),
        SimpleNamespace(code="fp3", name="Free Practice 3", start_time=base + timedelta(hours=8)),
        SimpleNamespace(
            code="qualifying_lmgt3", name="Qualifying - LMGT3",
            start_time=base + timedelta(hours=12),
        ),
        SimpleNamespace(
            code="hyperpole_lmgt3", name="Hyperpole - LMGT3",
            start_time=base + timedelta(hours=12, minutes=30),
        ),
        SimpleNamespace(
            code="qualifying_hypercar", name="Qualifying - Hypercar",
            start_time=base + timedelta(hours=13),
        ),
        SimpleNamespace(
            code="hyperpole_hypercar", name="Hyperpole - Hypercar",
            start_time=base + timedelta(hours=13, minutes=30),
        ),
        SimpleNamespace(code="race", name="Race", start_time=base + timedelta(days=1)),
    ]


def _wec_event(sessions=None):
    sessions = sessions if sessions is not None else _wec_sessions()
    return SimpleNamespace(
        sport="racing",
        league="wec",
        name="6 Hours of São Paulo",
        sessions=sessions,
    )


def test_isolate_stream_session_label():
    label = _isolate_stream_session_label(
        "AU (STAN 36) | Free Practice 3: 6 Hours of Sao Paulo WEC 2026 (2026-07-11 23:00:44)"
    )
    assert label == "Free Practice 3"


def test_isolate_stream_session_label_no_delimiters():
    assert _isolate_stream_session_label("HBO UK 065") == "HBO UK 065"


class TestSessionCategoryFromStreamName:
    def test_numbered_free_practice(self):
        assert _session_category_from_stream_name(
            "AU (STAN 36) | Free Practice 3: 6 Hours of Sao Paulo WEC 2026 (2026-07-11 23:00:44)"
        ) == "fp3"

    def test_bare_qualifying(self):
        assert _session_category_from_stream_name(
            "AU (STAN 39) | Qualifying: 6 Hours of Sao Paulo WEC 2026 (2026-07-12 03:20:29)"
        ) == "qualifying"

    def test_bare_race(self):
        name = "AU (STAN) | Race: 6 Hours of Sao Paulo"
        assert _session_category_from_stream_name(name) == "race"

    def test_generic_channel_name_has_no_hint(self):
        # Linear/whole-weekend channel names must not trip narrowing.
        name = "HBO UK 065|  6 HOURS OF SAO PAULO - FIA WEC | Round 5 | 6 Hours of Sao Paulo (2026-07-11 13:00:00)"  # noqa: E501
        assert _session_category_from_stream_name(name) is None

    def test_race_as_substring_of_unrelated_branding_has_no_hint(self):
        # "race" must only count as a label when it (near enough) stands
        # alone — not as a substring of generic branding text.
        assert _session_category_from_stream_name("Sky | Race Week Live: WEC coverage") is None

    def test_plain_channel_name_has_no_hint(self):
        assert _session_category_from_stream_name("ESPN 2 (US)") is None

    def test_trailing_qualifying_keyword(self):
        # NASCAR/TSN+ convention: session type as a trailing word in the
        # label, not the whole label (unlike tsdb/STAN's bare "Qualifying").
        assert _session_category_from_stream_name(
            "CA (TSN+ 021) | NASCAR Cup Series Qualifying: Quaker State 400 (2026-07-11 16:30:00)"
        ) == "qualifying"
        assert _session_category_from_stream_name(
            "CA (TSN+ 015) | 2026 NASCAR ORAP Series Qualifying: Focused Health 250 (2026-07-11 11:00:00)"  # noqa: E501
        ) == "qualifying"

    def test_trailing_unnumbered_practice_keyword(self):
        # NASCAR emits an unnumbered "practice" session code and TSN+ labels
        # the feed "<Series> Practice" (no digit) — this must scope to the
        # practice category, not fall into the generic fan-out where the
        # practice exclusion would drop it (the exact inversion: a dedicated
        # practice feed landing on Qualifying/Race but not Practice).
        assert _session_category_from_stream_name(
            "CA (TSN+ 021) | NASCAR Cup Series Practice: Quaker State 400 (2026-07-11 14:30:00)"
        ) == "practice"

    def test_trailing_practice_requires_word_boundary(self):
        # "...practice" as a word-suffix must not match ("Malpractice").
        assert _session_category_from_stream_name(
            "US | Malpractice: Medical Drama Marathon (2026-07-11 20:00:00)"
        ) is None

    def test_no_trailing_keyword_has_no_hint(self):
        # A label ending in descriptive text (not a session word) must not
        # trip the trailing fallback.
        assert _session_category_from_stream_name(
            "2026 NASCAR CRAFTSMAN Truck Series: LiUNA 150 (2026-07-11 13:00:00)"
        ) is None
        assert _session_category_from_stream_name(
            "CA (TSN+ 036) | NASCAR Cup Series On_Board Camera: Quaker State 400 (2026-07-12 19:00:00)"  # noqa: E501
        ) is None


class TestSessionInCategory:
    def test_numbered_fp_matches_exactly(self):
        assert _session_in_category("fp3", "fp3")
        assert not _session_in_category("fp1", "fp3")

    def test_qualifying_category_covers_class_suffixed_sessions(self):
        assert _session_in_category("qualifying_lmgt3", "qualifying")
        assert _session_in_category("qualifying_hypercar", "qualifying")
        assert not _session_in_category("fp1", "qualifying")

    def test_qualifying_category_also_covers_hyperpole(self):
        # WEC's Hyperpole is itself a qualifying shootout, and providers
        # rarely label it distinctly — a bare "Qualifying" stream is a real
        # candidate for a Hyperpole session too.
        assert _session_in_category("hyperpole_lmgt3", "qualifying")
        assert _session_in_category("hyperpole_hypercar", "qualifying")
        assert _session_in_category("hyperpole", "qualifying")
        # But a stream explicitly labeled "Hyperpole" stays scoped to
        # hyperpole sessions only — narrowing is not symmetric.
        assert not _session_in_category("qualifying_lmgt3", "hyperpole")


def test_expand_racing_segments_scopes_dedicated_fp3_stream():
    matched = [{"stream": {"id": 1, "name": "AU (STAN) | Free Practice 3: 6 Hours of Sao Paulo"},
                "event": _wec_event()}]
    out = expand_racing_segments(matched)
    assert [m["segment"] for m in out] == ["fp3"]


def test_expand_racing_segments_scopes_bare_qualifying_to_both_classes_and_hyperpole():
    matched = [{"stream": {"id": 1, "name": "AU (STAN) | Qualifying: 6 Hours of Sao Paulo"},
                "event": _wec_event()}]
    out = expand_racing_segments(matched)
    assert {m["segment"] for m in out} == {
        "qualifying_lmgt3", "qualifying_hypercar", "hyperpole_lmgt3", "hyperpole_hypercar",
    }


def test_expand_racing_segments_keeps_full_fanout_for_generic_channel_name_excluding_practice():
    # A generic/linear channel name still fans out across everything EXCEPT
    # practice — providers rarely carry a dedicated practice feed, so a
    # whole-weekend stream landing on a Practice channel is more likely to
    # be dead air than a real source; better no channel than that.
    matched = [{
        "stream": {"id": 1, "name": "HBO UK 065|  6 HOURS OF SAO PAULO - FIA WEC | Round 5"},
        "event": _wec_event(),
    }]
    out = expand_racing_segments(matched)
    assert {m["segment"] for m in out} == {
        "qualifying_lmgt3", "hyperpole_lmgt3", "qualifying_hypercar", "hyperpole_hypercar",
        "race",
    }


def test_expand_racing_segments_still_scopes_dedicated_practice_stream():
    # The exception: a stream whose name specifically names a practice
    # session still gets that session (already covered by
    # test_expand_racing_segments_scopes_dedicated_fp3_stream, asserted
    # again here alongside the generic-name exclusion for contrast).
    matched = [{"stream": {"id": 1, "name": "AU (STAN) | Free Practice 2: 6 Hours of Sao Paulo"},
                "event": _wec_event()}]
    out = expand_racing_segments(matched)
    assert [m["segment"] for m in out] == ["fp2"]


def test_expand_racing_segments_scopes_unnumbered_trailing_practice_stream():
    # NASCAR-style weekend: an unnumbered "practice" session plus qualifying
    # and race. A TSN+ "<Series> Practice" feed must land on the practice
    # channel only.
    base = datetime(2026, 7, 11, 9, tzinfo=UTC)
    sessions = [
        SimpleNamespace(code="practice", name="Practice", start_time=base),
        SimpleNamespace(code="qualifying", name="Qualifying", start_time=base + timedelta(hours=3)),
        SimpleNamespace(code="race", name="Race", start_time=base + timedelta(days=1)),
    ]
    matched = [{
        "stream": {"id": 1, "name": "CA (TSN+ 021) | NASCAR Cup Series Practice: Quaker State 400"},
        "event": _wec_event(sessions),
    }]
    out = expand_racing_segments(matched)
    assert [m["segment"] for m in out] == ["practice"]


def test_expand_racing_segments_drops_stream_when_no_session_of_the_category_exists():
    # Live false positive (Grand Prix of Nashville, 2026-07-17): ESPN's
    # IndyCar events carry only the race session, so dedicated "Practice 1:"
    # and "Qualifying:" streams found no session of their category and the
    # old fallback fanned them out to everything — all three landed as
    # sources on the Race channel. A stream that names a session category
    # the event doesn't have must be dropped, not rebound to other sessions.
    sessions = [s for s in _wec_sessions() if s.code != "fp3"]
    matched = [{"stream": {"id": 1, "name": "AU (STAN) | Free Practice 3: 6 Hours of Sao Paulo"},
                "event": _wec_event(sessions)}]
    out = expand_racing_segments(matched)
    assert out == []


def test_expand_racing_segments_drops_session_named_streams_for_race_only_event():
    # The exact Nashville shape: event has only a race session; the
    # practice/qualifying feeds disappear, the race feed stays.
    race = SimpleNamespace(code="race", name="Race",
                           start_time=datetime(2026, 7, 19, 21, 30, tzinfo=UTC))
    def entry(name):
        return {"stream": {"id": 1, "name": name}, "event": _wec_event([race])}
    out = expand_racing_segments([
        entry("AU (STAN 31) | Practice 1: Grand Prix of Nashville  Indycar 2026"),
        entry("AU (STAN 41) | Qualifying: Grand Prix of Nashville  Indycar 2026"),
        entry("AU (STAN 44) | Final Practice: Grand Prix of Nashville  Indycar 2026"),
        entry("AU (STAN 50) | Race: Grand Prix of Nashville  Indycar 2026"),
    ])
    assert [(m["stream"]["name"][:12], m["segment"]) for m in out] == [
        ("AU (STAN 50)", "race"),
    ]


class TestIsPracticeSession:
    def test_numbered_fp_codes(self):
        assert _is_practice_session("fp1")
        assert _is_practice_session("fp2")
        assert _is_practice_session("fp3")

    def test_bare_practice_code(self):
        assert _is_practice_session("practice")

    def test_non_practice_codes(self):
        assert not _is_practice_session("qualifying")
        assert not _is_practice_session("race")
        assert not _is_practice_session("hyperpole_lmgt3")
        assert not _is_practice_session("sprint")


def test_expand_racing_segments_produces_no_channel_when_only_practice_exists():
    # A single-session (practice-only) event matched by a generic stream:
    # rather than land the stream on a Practice channel with nothing airing
    # yet, no segment — and so no channel — should be produced at all.
    sessions = [
        SimpleNamespace(code="practice", name="Practice",
                        start_time=datetime(2026, 7, 11, 9, tzinfo=UTC)),
    ]
    matched = [{"stream": {"id": 1, "name": "TSN+ 016"}, "event": _wec_event(sessions)}]
    out = expand_racing_segments(matched)
    assert out == []


# ---------------------------------------------------------------------------
# Series scoping: a stream naming a specific series must only match that
# series' league(s) — and match nothing when that series isn't configured.
# ---------------------------------------------------------------------------


class TestDetectRacingSeriesLeagues:
    def test_motogp(self):
        assert detect_racing_series_leagues(
            "CA (SN+ 017) | MotoGP _ Grand Prix of Germany (2026-07-12 07:15:00)"
        ) == ("motogp",)

    def test_nascar_umbrella(self):
        assert detect_racing_series_leagues("NASCAR Cup Series at San Diego") == (
            "nascar-cup", "nascar-xfinity", "nascar-truck",
        )

    def test_f2_and_f3_are_distinct_from_f1(self):
        assert detect_racing_series_leagues("Formula 2 | Hungarian GP") == ("f2",)
        assert detect_racing_series_leagues("F3: Feature Race") == ("f3",)
        assert detect_racing_series_leagues("F1 | Monaco Grand Prix") == ("f1",)

    def test_wec(self):
        assert detect_racing_series_leagues("FIA WEC | ROUND 5") == ("wec",)
        assert detect_racing_series_leagues("World Endurance Championship") == ("wec",)

    def test_generic_grand_prix_is_unscoped(self):
        # "grand prix" is racing evidence but names no series — must stay
        # unscoped so a bare "Monaco Grand Prix" stream can still match F1.
        assert detect_racing_series_leagues("Monaco Grand Prix") is None

    def test_empty(self):
        assert detect_racing_series_leagues("") is None
        assert detect_racing_series_leagues("ESPN 2 (US)") is None


def _racing_group_matcher(leagues):
    from tests.fakes import make_stream_matcher

    return make_stream_matcher(
        leagues=tuple(leagues),
        league_event_types={lg: "event" for lg in leagues},
        league_sports={lg: "racing" for lg in leagues},
    )


def _matched_racing_outcome():
    from types import SimpleNamespace

    from apex.consumers.matching.result import MatchMethod, MatchOutcome

    event = SimpleNamespace(league="imsa", id="tsdb_imsa_2026_7", start_time=None,
                            short_name="Chevrolet Grand Prix")
    return MatchOutcome.matched(MatchMethod.FUZZY, event=event, confidence=0.9)


def test_racing_series_scoping_blocks_unconfigured_series(monkeypatch):
    # Live false-match regression (teamarr#394 follow-up): two "MotoGP -
    # Grand Prix of Germany" streams direct-matched IMSA's "Chevrolet Grand
    # Prix" — the only racing event covering the date — because motogp isn't
    # a configured league and the shared "Grand Prix" tokens cleared the
    # single-event sanity bar. A stream naming an unconfigured series must
    # match nothing.
    m = _racing_group_matcher(["imsa", "wec"])
    racing_called = []
    monkeypatch.setattr(
        m._racing_matcher, "match",
        lambda **kw: racing_called.append(kw["league"]) or _matched_racing_outcome(),
    )

    rc = classify_stream(
        "CA (SN+ 017) | MotoGP _ Grand Prix of Germany (2026-07-12 07:15:00)", "event"
    )
    assert rc.category == StreamCategory.RACING_EVENT
    out = m._match_racing_event(rc, 1, date(2026, 7, 12))
    assert not racing_called  # imsa/wec must never be attempted
    assert not out.is_matched


def test_racing_series_scoping_restricts_to_named_league(monkeypatch):
    # A stream naming IMSA in a group with several racing leagues must only
    # try imsa — not fan out across the others.
    m = _racing_group_matcher(["f1", "imsa", "wec"])
    racing_called = []
    monkeypatch.setattr(
        m._racing_matcher, "match",
        lambda **kw: racing_called.append(kw["league"]) or _matched_racing_outcome(),
    )

    rc = classify_stream(
        "US (Peacock 031) | IMSA CTMP Grand Prix (2026-07-12 14:00:00)", "event"
    )
    out = m._match_racing_event(rc, 1, date(2026, 7, 12))
    assert racing_called == ["imsa"]
    assert out.is_matched


def test_racing_generic_name_stays_unscoped(monkeypatch):
    # No series named ("Monaco Grand Prix") → all racing leagues remain
    # eligible, preserving pre-scoping behavior.
    m = _racing_group_matcher(["f1"])
    racing_called = []
    monkeypatch.setattr(
        m._racing_matcher, "match",
        lambda **kw: racing_called.append(kw["league"]) or _matched_racing_outcome(),
    )

    rc = classify_stream("Monaco Grand Prix (2026-06-01 13:00:00)", "event")
    out = m._match_racing_event(rc, 1, date(2026, 6, 1))
    assert racing_called == ["f1"]
    assert out.is_matched


# ---------------------------------------------------------------------------
# expand_racing_segments: EPG-matched entries scope by their programme slot
#
# Live gap (Belgian GP FP1, 2026-07-17): an EPG-matched linear channel ("Sky
# Sports F1 HD") names no session in its STREAM name, so it took the generic
# fan-out — which excludes practice — and FP1 aired with no channel. The
# guide programme IS positive evidence of coverage ("…: 1st Practice" at the
# session's slot), so EPG entries scope to the session(s) their programme
# window covers, practice included.
# ---------------------------------------------------------------------------


def _belgian_sessions():
    return [
        SimpleNamespace(code="fp1", name="Practice 1",
                        start_time=datetime(2026, 7, 17, 11, 30, tzinfo=UTC)),
        SimpleNamespace(code="fp2", name="Practice 2",
                        start_time=datetime(2026, 7, 17, 15, 0, tzinfo=UTC)),
        SimpleNamespace(code="qualifying", name="Qualifying",
                        start_time=datetime(2026, 7, 18, 14, 0, tzinfo=UTC)),
        SimpleNamespace(code="race", name="Race",
                        start_time=datetime(2026, 7, 19, 13, 0, tzinfo=UTC)),
    ]


def _epg_entry(prog_start, prog_end):
    return {
        "stream": {"id": 1, "name": "Sky Sports F1 HD"},
        "event": _wec_event(_belgian_sessions()),
        "match_method": "epg",
        "epg_program_start": prog_start,
        "epg_program_end": prog_end,
    }


def test_epg_entry_scopes_to_practice_session_its_programme_covers():
    # "Live: Formula 1 | Belgian Grand Prix: 1st Practice" 11:00–12:55 UTC.
    out = expand_racing_segments([_epg_entry(
        datetime(2026, 7, 17, 11, 0, tzinfo=UTC),
        datetime(2026, 7, 17, 12, 55, tzinfo=UTC),
    )])
    assert [m["segment"] for m in out] == ["fp1"]


def test_epg_entry_scopes_to_race_for_race_slot():
    out = expand_racing_segments([_epg_entry(
        datetime(2026, 7, 19, 12, 30, tzinfo=UTC),
        datetime(2026, 7, 19, 15, 30, tzinfo=UTC),
    )])
    assert [m["segment"] for m in out] == ["race"]


def test_epg_buildup_programme_binds_to_nearest_session_within_tolerance():
    # Pre-race build-up that ENDS before lights out (no window overlap) —
    # the anchor gate admitted it, so it binds to the nearest session.
    out = expand_racing_segments([_epg_entry(
        datetime(2026, 7, 19, 11, 30, tzinfo=UTC),
        datetime(2026, 7, 19, 12, 50, tzinfo=UTC),
    )])
    assert [m["segment"] for m in out] == ["race"]


def test_epg_entry_covering_no_session_is_dropped():
    # A slot hours from every session (stale plan entry): no channel at all
    # beats a wrong one.
    out = expand_racing_segments([_epg_entry(
        datetime(2026, 7, 18, 2, 0, tzinfo=UTC),
        datetime(2026, 7, 18, 3, 0, tzinfo=UTC),
    )])
    assert out == []


def test_name_path_generic_stream_still_excludes_practice():
    # Non-EPG entry (no match_method/window): generic fan-out minus practice,
    # unchanged.
    entry = {
        "stream": {"id": 1, "name": "Sky Sports F1 HD"},
        "event": _wec_event(_belgian_sessions()),
    }
    out = expand_racing_segments([entry])
    assert {m["segment"] for m in out} == {"qualifying", "race"}


# ------------------------------------------------------------ nearest_session


def test_nearest_session_inside_window_is_zero_distance():
    event = _wec_event(_belgian_sessions())
    code, dist = nearest_session(event, datetime(2026, 7, 17, 11, 45, tzinfo=UTC))
    assert code == "fp1" and dist == 0.0


def test_nearest_session_picks_closest_edge():
    event = _wec_event(_belgian_sessions())
    # 14:40 UTC Friday: FP1 ended 12:30 (7800s away), FP2 starts 15:00 (1200s).
    code, dist = nearest_session(event, datetime(2026, 7, 17, 14, 40, tzinfo=UTC))
    assert code == "fp2" and dist == 1200.0


def test_nearest_session_no_sessions():
    event = _wec_event([])
    code, dist = nearest_session(event, datetime(2026, 7, 17, 11, 45, tzinfo=UTC))
    assert code is None and dist == float("inf")


# ---------------------------------------------------------------------------
# Session scoping: Apple-TV-PPV "<tag> | <COUNTRY>: <SESSION> | ..." names
# ---------------------------------------------------------------------------


class TestColonValueSessionLabels:
    def test_apple_tv_race_stream_scopes_to_race(self):
        assert _session_category_from_stream_name(
            "NEXT | BELGIUM: RACE | Sun 19 Jul 11:50 UTC (UK) | 8K EXCLUSIVE "
            "| UK: APPLE TV F1 PPV 1"
        ) == "race"

    def test_apple_tv_sprint_stream_scopes_to_sprint(self):
        assert _session_category_from_stream_name(
            "NEXT | NETHERLANDS: SPRINT | Sat 22 Aug 09:15 UTC (UK) | 8K EXCLUSIVE "
            "| UK: APPLE TV F1 PPV 3"
        ) == "sprint"

    def test_session_word_embedded_in_branding_does_not_count(self):
        # "RACING"/"Race" inside branding text is not an anchored field match.
        assert _session_category_from_stream_name(
            "UK ★ SKY SPORTS F1 RACING HD"
        ) is None
        assert _session_category_from_stream_name(
            "US: Racecourse Network | Live: Horse Coverage"
        ) is None

    def test_timestamp_colons_do_not_confuse_field_scan(self):
        # "11:50" splits into non-session fields; a generic linear name with
        # times must keep the full fan-out.
        assert _session_category_from_stream_name(
            "HBO UK 065 | Live 11:50 | Grand Prix Coverage"
        ) is None


def test_expand_scopes_apple_tv_race_stream_to_race_only():
    # Live: "NEXT | BELGIUM: RACE ..." PPV streams (name-path matches) were
    # fanned out generically and landed as full-life sources on the
    # Qualifying channel too.
    entry = {
        "stream": {"id": 1, "name": "NEXT | BELGIUM: RACE | Sun 19 Jul 11:50 UTC (UK) "
                   "| 8K EXCLUSIVE | UK: APPLE TV F1 PPV 1"},
        "event": _wec_event(_belgian_sessions()),
    }
    out = expand_racing_segments([entry])
    assert [m["segment"] for m in out] == ["race"]
