"""
Ripper Media Player Integration Package.
Controls PotPlayer, VLC, and MPV execution with subtitle and audio language flags.
"""
from .launcher import (
    find_potplayer_in_registry,
    detect_available_players,
    launch_video_stream_in_player,
    save_playback_resume_state,
    get_playback_resume_state,
    POTPLAYER_COMMON_PATHS,
    VLC_COMMON_PATHS,
    MPV_COMMON_PATHS,
)

__all__ = [
    "find_potplayer_in_registry",
    "detect_available_players",
    "launch_video_stream_in_player",
    "save_playback_resume_state",
    "get_playback_resume_state",
    "POTPLAYER_COMMON_PATHS",
    "VLC_COMMON_PATHS",
    "MPV_COMMON_PATHS",
]