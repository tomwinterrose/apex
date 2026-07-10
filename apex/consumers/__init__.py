"""Consumer layer - EPG generation, matching, channels."""

from apex.consumers.cache import (
    CacheRefresher,
    CacheStats,
    LeagueEntry,
    TeamEntry,
    TeamLeagueCache,
    expand_leagues,
    find_leagues_for_stream,
    get_cache,
    refresh_cache,
    refresh_cache_if_needed,
)
from apex.consumers.channel_lifecycle import (
    ChannelCreationResult,
    ChannelLifecycleManager,
    ChannelLifecycleService,
    CreateTiming,
    DeleteTiming,
    DuplicateMode,
    LifecycleDecision,
    StreamProcessResult,
    create_lifecycle_service,
    generate_event_tvg_id,
    get_lifecycle_settings,
    slugify_keyword,
)
from apex.consumers.event_epg import (
    EventChannelInfo,
    EventEPGGenerator,
    EventEPGOptions,
)
from apex.consumers.event_group_processor import (
    BatchProcessingResult,
    EventGroupProcessor,
    ProcessingResult,
    process_all_event_groups,
    process_event_group,
)
from apex.consumers.event_matcher import EventMatcher
from apex.consumers.filler import (
    ConditionalFillerTemplate,
    FillerConfig,
    FillerGenerator,
    FillerOptions,
    FillerTemplate,
    FillerType,
    OffseasonFillerTemplate,
)
from apex.consumers.generation import (
    GenerationResult as FullGenerationResult,
)
from apex.consumers.generation import (
    run_full_generation,
)
from apex.consumers.matching import (
    BatchMatchResult,
    MatchedStreamResult,
    StreamMatcher,
)
from apex.consumers.reconciliation import (
    ChannelReconciler,
    ReconciliationIssue,
    ReconciliationResult,
    create_reconciler,
    detect_stale_groups,
)
from apex.consumers.scheduler import (
    LifecycleScheduler,
    get_scheduler_status,
    is_scheduler_running,
    start_lifecycle_scheduler,
    stop_lifecycle_scheduler,
)
from apex.consumers.stream_match_cache import (
    StreamCacheEntry,
    StreamMatchCache,
    compute_fingerprint,
    event_to_cache_data,
    get_generation_counter,
    increment_generation_counter,
)
from apex.consumers.team_epg import TeamEPGGenerator, TeamEPGOptions
from apex.consumers.team_processor import (
    BatchTeamResult,
    TeamProcessingResult,
    TeamProcessor,
    get_all_team_xmltv,
    process_all_teams,
    process_team,
)
from apex.core import TemplateConfig
from apex.database.templates import EventTemplateConfig

__all__ = [
    # Channel lifecycle
    "ChannelCreationResult",
    "ChannelLifecycleManager",
    "ChannelLifecycleService",
    "CreateTiming",
    "DeleteTiming",
    "DuplicateMode",
    "LifecycleDecision",
    "StreamProcessResult",
    "create_lifecycle_service",
    "generate_event_tvg_id",
    "slugify_keyword",
    "get_lifecycle_settings",
    # Stream matching
    "StreamMatcher",
    "MatchedStreamResult",
    "BatchMatchResult",
    # Stream match cache
    "StreamCacheEntry",
    "StreamMatchCache",
    "compute_fingerprint",
    "event_to_cache_data",
    "get_generation_counter",
    "increment_generation_counter",
    # Team/league cache
    "CacheRefresher",
    "CacheStats",
    "LeagueEntry",
    "TeamEntry",
    "TeamLeagueCache",
    "expand_leagues",
    "find_leagues_for_stream",
    "get_cache",
    "refresh_cache",
    "refresh_cache_if_needed",
    # Filler generation
    "ConditionalFillerTemplate",
    "FillerConfig",
    "FillerGenerator",
    "FillerOptions",
    "FillerTemplate",
    "FillerType",
    "OffseasonFillerTemplate",
    # Event-based EPG
    "EventChannelInfo",
    "EventEPGGenerator",
    "EventEPGOptions",
    "EventMatcher",
    "EventTemplateConfig",
    # Event group processing
    "BatchProcessingResult",
    "EventGroupProcessor",
    "ProcessingResult",
    "process_all_event_groups",
    "process_event_group",
    # Reconciliation
    "ChannelReconciler",
    "detect_stale_groups",
    "ReconciliationIssue",
    "ReconciliationResult",
    "create_reconciler",
    # Scheduler
    "LifecycleScheduler",
    "get_scheduler_status",
    "is_scheduler_running",
    "start_lifecycle_scheduler",
    "stop_lifecycle_scheduler",
    # Team-based EPG
    "TeamEPGGenerator",
    "TeamEPGOptions",
    "TemplateConfig",
    # Unified generation
    "FullGenerationResult",
    "run_full_generation",
    # Team processing
    "BatchTeamResult",
    "TeamProcessor",
    "TeamProcessingResult",
    "get_all_team_xmltv",
    "process_all_teams",
    "process_team",
]
