"""Database layer."""

from apex.database.aliases import (
    TeamAlias,
    bulk_create_aliases,
    create_alias,
    delete_alias,
    export_aliases,
    get_alias,
    get_alias_by_text,
    list_aliases,
    update_alias,
)
from apex.database.connection import get_connection, get_db, init_db, reset_db
from apex.database.leagues import (
    LeagueMapping,
    get_league_mapping,
    get_leagues_for_provider,
    provider_supports_league,
)
from apex.database.settings import (
    AllSettings,
    DispatcharrSettings,
    DurationSettings,
    EPGSettings,
    LifecycleSettings,
    ReconciliationSettings,
    SchedulerSettings,
    get_all_settings,
    get_dispatcharr_settings,
    get_epg_settings,
    get_lifecycle_settings,
    get_scheduler_settings,
)
from apex.database.templates import (
    EventTemplateConfig,
    Template,
    create_template,
    delete_template,
    get_all_templates,
    get_template,
    get_template_by_name,
    get_templates_for_league,
    get_templates_for_sport,
    seed_default_templates,
    template_to_event_config,
    template_to_filler_config,
    update_template,
)

__all__ = [
    # Aliases
    "TeamAlias",
    "bulk_create_aliases",
    "create_alias",
    "delete_alias",
    "export_aliases",
    "get_alias",
    "get_alias_by_text",
    "list_aliases",
    "update_alias",
    # Connection
    "get_connection",
    "get_db",
    "init_db",
    "reset_db",
    # Leagues
    "LeagueMapping",
    "get_league_mapping",
    "get_leagues_for_provider",
    "provider_supports_league",
    # Settings
    "AllSettings",
    "DispatcharrSettings",
    "DurationSettings",
    "EPGSettings",
    "LifecycleSettings",
    "ReconciliationSettings",
    "SchedulerSettings",
    "get_all_settings",
    "get_dispatcharr_settings",
    "get_epg_settings",
    "get_lifecycle_settings",
    "get_scheduler_settings",
    # Templates
    "EventTemplateConfig",
    "Template",
    "create_template",
    "delete_template",
    "get_all_templates",
    "get_template",
    "get_template_by_name",
    "get_templates_for_league",
    "get_templates_for_sport",
    "seed_default_templates",
    "template_to_event_config",
    "template_to_filler_config",
    "update_template",
]
