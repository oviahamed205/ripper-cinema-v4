"""
System Environment & Media Player Probe.
Discovers installed video players, system language locale, and displays.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass(frozen=True)
class DetectedPlayerInfo:
    name: str
    executable_path: str
    is_potplayer: bool = False
    is_vlc: bool = False
    is_mpv: bool = False


KNOWN_PLAYER_PATHS = [
    # PotPlayer 64-bit & 32-bit
    ("PotPlayer 64-bit", r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe"),
    ("PotPlayer", r"C:\Program Files (x86)\DAUM\PotPlayer\PotPlayerMini.exe"),
    ("PotPlayer", r"C:\Program Files\PotPlayer\PotPlayerMini64.exe"),
    # VLC Media Player
    ("VLC Media Player", r"C:\Program Files\VideoLAN\VLC\vlc.exe"),
    ("VLC Media Player", r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"),
    # MPV Player
    ("MPV Player", r"C:\Program Files\mpv\mpv.exe"),
    ("MPV Player", r"C:\mpv\mpv.exe"),
]


def detect_system_players() -> List[DetectedPlayerInfo]:
    """Scans Windows file system and paths to discover installed video players."""
    found: List[DetectedPlayerInfo] = []

    for name, p in KNOWN_PLAYER_PATHS:
        if os.path.exists(p):
            found.append(DetectedPlayerInfo(
                name=name,
                executable_path=p,
                is_potplayer="potplayer" in name.lower(),
                is_vlc="vlc" in name.lower(),
                is_mpv="mpv" in name.lower(),
            ))

    # Also check PATH environment variable
    for binary, name in [("potplayer", "PotPlayer"), ("vlc", "VLC Media Player"), ("mpv", "MPV Player")]:
        from shutil import which
        loc = which(binary)
        if loc and os.path.exists(loc):
            if not any(f.executable_path.lower() == loc.lower() for f in found):
                found.append(DetectedPlayerInfo(
                    name=name,
                    executable_path=loc,
                    is_potplayer="potplayer" in name.lower(),
                    is_vlc="vlc" in name.lower(),
                    is_mpv="mpv" in name.lower(),
                ))

    return found


def get_preferred_primary_player() -> Optional[DetectedPlayerInfo]:
    """Returns the #1 preferred player (PotPlayer prioritized, then VLC, then MPV)."""
    players = detect_system_players()
    if not players:
        return None
    # Prioritize PotPlayer
    for p in players:
        if p.is_potplayer:
            return p
    return players[0]
