"""Dispatcharr API client package.

Provides authenticated access to Dispatcharr API with:
- Automatic token management and refresh
- Exponential backoff retry for transient errors
- High-level managers for channels, EPG, M3U, and logos
- Caching for efficient batch operations

Usage:
    from apex.dispatcharr import DispatcharrClient, ChannelManager

    with DispatcharrClient("http://localhost:9191", "admin", "pass") as client:
        channels = ChannelManager(client)
        channels.clear_cache()

        result = channels.create_channel(
            name="Giants @ Cowboys",
            channel_number=5001,
            stream_ids=[456],
            tvg_id="apex-event-12345"
        )

        if result.success:
            logger.info("[DISPATCHARR] Created channel: %s", result.channel)
"""

from apex.dispatcharr.auth import TokenManager
from apex.dispatcharr.client import DispatcharrClient
from apex.dispatcharr.factory import (
    ConnectionTestResult,
    DispatcharrConnection,
    DispatcharrFactory,
    close_dispatcharr,
    get_dispatcharr_client,
    get_dispatcharr_connection,
    get_factory,
    test_dispatcharr_connection,
)
from apex.dispatcharr.managers import (
    ChannelCache,
    ChannelManager,
    EPGManager,
    LogoManager,
    M3UManager,
)
from apex.dispatcharr.types import (
    BatchRefreshResult,
    DispatcharrChannel,
    DispatcharrChannelGroup,
    DispatcharrChannelProfile,
    DispatcharrEPGData,
    DispatcharrEPGSource,
    DispatcharrLogo,
    DispatcharrM3UAccount,
    DispatcharrStream,
    OperationResult,
    RefreshResult,
)

__all__ = [
    # Client
    "DispatcharrClient",
    "TokenManager",
    # Factory
    "ConnectionTestResult",
    "DispatcharrConnection",
    "DispatcharrFactory",
    "close_dispatcharr",
    "get_dispatcharr_client",
    "get_dispatcharr_connection",
    "get_factory",
    "test_dispatcharr_connection",
    # Managers
    "ChannelCache",
    "ChannelManager",
    "EPGManager",
    "LogoManager",
    "M3UManager",
    # Types
    "BatchRefreshResult",
    "DispatcharrChannel",
    "DispatcharrChannelGroup",
    "DispatcharrChannelProfile",
    "DispatcharrEPGData",
    "DispatcharrEPGSource",
    "DispatcharrLogo",
    "DispatcharrM3UAccount",
    "DispatcharrStream",
    "OperationResult",
    "RefreshResult",
]
