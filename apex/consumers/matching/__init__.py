"""Stream matching module.

Provides stream-to-event matching with classification, normalization,
and result tracking.

Main entry point:
    from apex.consumers.matching import StreamMatcher

    matcher = StreamMatcher(service, db_factory, group_id, search_leagues)
    result = matcher.match_all(streams, target_date)
"""

from apex.consumers.matching.classifier import (
    ClassifiedStream,
    StreamCategory,
    classify_stream,
    classify_streams,
)
from apex.consumers.matching.constants import (
    ACCEPT_WITH_DATE_THRESHOLD,
    BOTH_TEAMS_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    MATCH_WINDOW_DAYS,
)
from apex.consumers.matching.epg_index import EPGProgramIndex
from apex.consumers.matching.event_matcher import (
    EventCardMatcher,
    EventMatchContext,
)
from apex.consumers.matching.matcher import (
    BatchMatchResult,
    MatchedStreamResult,
    StreamMatcher,
)
from apex.consumers.matching.normalizer import (
    NormalizedStream,
    normalize_for_matching,
    normalize_stream,
)
from apex.consumers.matching.result import (
    FailedReason,
    FilteredReason,
    MatchMethod,
    MatchOutcome,
    ResultAggregator,
    ResultCategory,
)
from apex.consumers.matching.team_matcher import (
    MatchContext,
    TeamMatcher,
)

__all__ = [
    # Constants
    "MATCH_WINDOW_DAYS",
    "HIGH_CONFIDENCE_THRESHOLD",
    "ACCEPT_WITH_DATE_THRESHOLD",
    "BOTH_TEAMS_THRESHOLD",
    # Main entry point
    "StreamMatcher",
    "MatchedStreamResult",
    "BatchMatchResult",
    # Result types
    "ResultCategory",
    "FilteredReason",
    "FailedReason",
    "MatchMethod",
    "MatchOutcome",
    "ResultAggregator",
    # Normalizer
    "NormalizedStream",
    "normalize_stream",
    "normalize_for_matching",
    # Classifier
    "StreamCategory",
    "ClassifiedStream",
    "classify_stream",
    "classify_streams",
    # TeamMatcher
    "TeamMatcher",
    "MatchContext",
    # EventCardMatcher
    "EventCardMatcher",
    "EventMatchContext",
    # EPG program index
    "EPGProgramIndex",
]
