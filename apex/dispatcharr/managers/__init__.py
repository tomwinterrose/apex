"""Dispatcharr API managers.

High-level managers for Dispatcharr operations:
- ChannelManager: Channel CRUD with caching
- EPGManager: EPG source operations
- M3UManager: M3U accounts and streams
- LogoManager: Logo upload/delete
"""

from apex.dispatcharr.managers.channels import ChannelCache, ChannelManager
from apex.dispatcharr.managers.epg import EPGManager
from apex.dispatcharr.managers.logos import LogoManager
from apex.dispatcharr.managers.m3u import M3UManager

__all__ = [
    "ChannelCache",
    "ChannelManager",
    "EPGManager",
    "LogoManager",
    "M3UManager",
]
