"""ESPN provider constants."""

# Map ESPN status names to our canonical states
STATUS_MAP = {
    "STATUS_SCHEDULED": "scheduled",
    "STATUS_IN_PROGRESS": "live",
    "STATUS_HALFTIME": "live",
    "STATUS_END_PERIOD": "live",
    "STATUS_FINAL": "final",
    "STATUS_FINAL_OT": "final",
    "STATUS_FULL_TIME": "final",  # Soccer
    "STATUS_FULL_TIME_ET": "final",  # Soccer extra time
    "STATUS_FULL_PEN": "final",  # Soccer penalties
    "STATUS_ABANDONED": "cancelled",  # Soccer
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "cancelled",
    "STATUS_DELAYED": "scheduled",
}

# Sports that are tournament-based (no home/away teams)
TOURNAMENT_SPORTS = {"tennis", "golf", "racing"}
