"""
Ripper TV Series & Anime Matrix Package.
Parses multi-season episode tables, batch zip packs, and generates sequential player playlists.
"""
from ..tv_parser import TVSeriesParser
from .playlist import generate_m3u_playlist

__all__ = [
    "TVSeriesParser",
    "generate_m3u_playlist",
]