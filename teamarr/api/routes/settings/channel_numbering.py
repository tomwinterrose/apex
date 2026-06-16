"""Channel numbering settings endpoints."""

from fastapi import APIRouter, HTTPException, status

from teamarr.database import get_db

from .models import (
    ChannelNumberingSettingsModel,
    ChannelNumberingSettingsUpdate,
)

router = APIRouter()

VALID_CHANNEL_MODES = {"auto", "manual"}
VALID_CONSOLIDATION_MODES = {"consolidate", "separate"}


@router.get("/settings/channel-numbering", response_model=ChannelNumberingSettingsModel)
def get_channel_numbering_settings():
    """Get channel numbering and consolidation settings."""
    from teamarr.database.settings import get_channel_numbering_settings

    with get_db() as conn:
        settings = get_channel_numbering_settings(conn)

    return ChannelNumberingSettingsModel(
        global_channel_mode=settings.global_channel_mode,
        league_channel_starts=settings.league_channel_starts,
        global_consolidation_mode=settings.global_consolidation_mode,
    )


@router.put("/settings/channel-numbering", response_model=ChannelNumberingSettingsModel)
def update_channel_numbering_settings(update: ChannelNumberingSettingsUpdate):
    """Update channel numbering and consolidation settings."""
    from teamarr.database.settings import (
        get_channel_numbering_settings,
        update_channel_numbering_settings,
    )

    if update.global_channel_mode is not None:
        if update.global_channel_mode not in VALID_CHANNEL_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid global_channel_mode. Valid: {VALID_CHANNEL_MODES}",
            )

    if update.global_consolidation_mode is not None:
        if update.global_consolidation_mode not in VALID_CONSOLIDATION_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid global_consolidation_mode. Valid: {VALID_CONSOLIDATION_MODES}",
            )

    with get_db() as conn:
        update_channel_numbering_settings(
            conn,
            global_channel_mode=update.global_channel_mode,
            league_channel_starts=update.league_channel_starts,
            global_consolidation_mode=update.global_consolidation_mode,
        )

    with get_db() as conn:
        settings = get_channel_numbering_settings(conn)

    return ChannelNumberingSettingsModel(
        global_channel_mode=settings.global_channel_mode,
        league_channel_starts=settings.league_channel_starts,
        global_consolidation_mode=settings.global_consolidation_mode,
    )
