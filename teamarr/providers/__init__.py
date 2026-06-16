"""Provider layer - sports data providers.

This is the SINGLE place where providers are configured and registered.
All other code discovers providers via ProviderRegistry.

Adding a new provider:
1. Create provider module (providers/newprovider/)
2. Register it here using ProviderRegistry.register()
3. Add league config to database (leagues table)

The rest of the system automatically discovers and uses registered providers.

Dependency Injection:
ProviderRegistry.initialize() must be called during app startup
to inject the LeagueMappingSource into providers.
"""

from teamarr.providers.espn import ESPNClient, ESPNProvider
from teamarr.providers.registry import ProviderConfig, ProviderRegistry
from teamarr.providers.static import StaticCalendarProvider
from teamarr.providers.tsdb import RateLimitStats, TSDBClient, TSDBProvider

# =============================================================================
# PROVIDER FACTORY FUNCTIONS
# =============================================================================
# Factories inject dependencies from the registry at instantiation time.


def _create_espn_provider() -> ESPNProvider:
    """Factory for ESPN provider with injected dependencies."""
    return ESPNProvider(
        league_mapping_source=ProviderRegistry.get_league_mapping_source(),
    )


def _get_tsdb_api_key() -> str | None:
    """Fetch TSDB API key from database settings.

    This is the boundary where database access happens before
    passing to the provider layer (which should not access database).
    """
    try:
        from teamarr.database import get_db

        with get_db() as conn:
            cursor = conn.execute("SELECT tsdb_api_key FROM settings WHERE id = 1")
            row = cursor.fetchone()
            if row and row["tsdb_api_key"]:
                return row["tsdb_api_key"]
    except Exception:
        # Database not available or column doesn't exist yet - expected during startup
        # No logging here to avoid noise during initialization
        pass
    return None


def _create_tsdb_team_name_resolver() -> callable:
    """Create a team name resolver callback for TSDB provider.

    This callback accesses the database, keeping DB access at the factory
    boundary rather than inside the provider layer.
    """
    from teamarr.database import get_db
    from teamarr.database.team_cache import get_team_name_by_id

    def resolver(team_id: str, league: str) -> str | None:
        with get_db() as conn:
            return get_team_name_by_id(conn, team_id, league, provider="tsdb")

    return resolver


def _create_tsdb_provider() -> TSDBProvider:
    """Factory for TSDB provider with injected dependencies."""
    return TSDBProvider(
        league_mapping_source=ProviderRegistry.get_league_mapping_source(),
        api_key=_get_tsdb_api_key(),
        team_name_resolver=_create_tsdb_team_name_resolver(),
    )


def _create_static_calendar_provider() -> StaticCalendarProvider:
    """Factory for static calendar provider with injected dependencies."""
    return StaticCalendarProvider(
        league_mapping_source=ProviderRegistry.get_league_mapping_source(),
    )


# =============================================================================
# PROVIDER REGISTRATION
# =============================================================================
# This is the ONLY place providers need to be added.
# Priority: Lower = higher priority (tried first for matching leagues)

ProviderRegistry.register(
    name="espn",
    provider_class=ESPNProvider,
    factory=_create_espn_provider,
    priority=0,  # Primary provider
    enabled=True,
)

ProviderRegistry.register(
    name="tsdb",
    provider_class=TSDBProvider,
    factory=_create_tsdb_provider,
    priority=100,  # IMSA, WEC, and other motorsports leagues
    enabled=True,
)

ProviderRegistry.register(
    name="static",
    provider_class=StaticCalendarProvider,
    factory=_create_static_calendar_provider,
    priority=110,  # Hand-maintained calendars for leagues with no live API (IMSA, WEC)
    enabled=True,
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Registry
    "ProviderConfig",
    "ProviderRegistry",
    # ESPN
    "ESPNClient",
    "ESPNProvider",
    # Static calendar (IMSA, WEC)
    "StaticCalendarProvider",
    # TheSportsDB
    "RateLimitStats",
    "TSDBClient",
    "TSDBProvider",
]
