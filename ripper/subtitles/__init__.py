"""
Ripper Subtitle Auto-Sync Package.
"""
from .sync import (
    search_subtitles,
    find_local_subtitle,
    download_subtitle_file,
    auto_fetch_and_load_subtitle,
    SUBTITLES_DIR,
)
from .engine import SubtitleEngine, normalize_subtitle_encoding
from .audio_tracks import (
    AudioTrackInfo,
    parse_audio_languages_from_title,
    probe_remote_stream_audio_tracks,
    LANGUAGE_MAP,
)

__all__ = [
    "search_subtitles",
    "find_local_subtitle",
    "download_subtitle_file",
    "auto_fetch_and_load_subtitle",
    "SUBTITLES_DIR",
    "SubtitleEngine",
    "normalize_subtitle_encoding",
    "AudioTrackInfo",
    "parse_audio_languages_from_title",
    "probe_remote_stream_audio_tracks",
    "LANGUAGE_MAP",
]