"""
M3U / PLS Sequential Episode Playlist Generator for PotPlayer & VLC.
Generates local playlist files so users can binge-watch entire seasons with auto-advance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any


def generate_m3u_playlist(title: str, episodes: List[Dict[str, Any]], output_path: Path) -> Path:
    """
    Generate an extended M3U playlist file for sequential player bingeing.
    episodes list contains dicts with {'title': str, 'url': str, 'duration': int}.
    """
    lines = ["#EXTM3U", f"#PLAYLIST:{title}"]
    for ep in episodes:
        ep_title = ep.get("title", "Episode")
        ep_url = ep.get("url", "")
        duration = ep.get("duration", -1)
        if ep_url:
            lines.append(f"#EXTINF:{duration},{ep_title}")
            lines.append(ep_url)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path