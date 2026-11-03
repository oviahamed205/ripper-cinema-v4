"""
TV Series Matrix & Batch Season Pack Parser
Features:
- Extracts Season & Episode grids (S01E01, S01E02)
- Extracts Complete Season Zip / Batch Download Packs
- Maps multi-quality tiers (480p, 720p, 1080p, 4K)
"""

import re
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup

class TVSeriesParser:

    @staticmethod
    def parse_tv_page(html_content: str, base_url: str) -> Dict[str, Any]:
        """Parses a movie/series page to extract seasons, episodes, and batch zip packs."""
        soup = BeautifulSoup(html_content, "html.parser")
        seasons_data: Dict[int, Dict[str, Any]] = {}

        # 1. Look for Season headings or tabs
        headings = soup.find_all(["h2", "h3", "h4", "h5", "strong", "p", "div", "button"])
        
        current_season = 1
        for el in headings:
            text = el.get_text().strip()
            s_match = re.search(r"(?:season|s)\s*(\d{1,2})", text, re.IGNORECASE)
            if s_match:
                try:
                    current_season = int(s_match.group(1))
                except ValueError:
                    pass

            if current_season not in seasons_data:
                seasons_data[current_season] = {
                    "season": current_season,
                    "episodes": {},
                    "zip_packs": []
                }

            # Check for zip pack links in parent/next siblings
            parent = el.find_parent(["div", "p", "section"]) or el
            for a in parent.find_all("a", href=True):
                a_text = a.get_text().strip()
                href = a["href"]
                if not href or href.startswith("#") or href.startswith("javascript"):
                    continue

                if any(k in a_text.lower() for k in ["zip", "batch", "pack", "complete season", "all episodes"]):
                    quality = "720p"
                    q_m = re.search(r"(480p|720p|1080p|4k)", a_text, re.I)
                    if q_m:
                        quality = q_m.group(1).upper()
                    seasons_data[current_season]["zip_packs"].append({
                        "title": a_text,
                        "url": href,
                        "quality": quality
                    })
                else:
                    # Check for single episode links
                    ep_m = re.search(r"(?:episode|ep|e)\s*(\d{1,3})", a_text, re.I)
                    if ep_m:
                        ep_num = int(ep_m.group(1))
                        quality = "1080p"
                        q_m = re.search(r"(480p|720p|1080p|4k)", a_text, re.I)
                        if q_m:
                            quality = q_m.group(1).upper()
                        
                        if ep_num not in seasons_data[current_season]["episodes"]:
                            seasons_data[current_season]["episodes"][ep_num] = {
                                "episode": ep_num,
                                "links": []
                            }
                        seasons_data[current_season]["episodes"][ep_num]["links"].append({
                            "quality": quality,
                            "url": href,
                            "label": a_text
                        })

        return seasons_data

    @staticmethod
    def generate_m3u_playlist(
        series_title: str,
        season_num: int,
        episodes: List[Dict[str, Any]],
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Generate .m3u binge-watch playlist file for PotPlayer/VLC.
        episodes: list of {"episode": int, "title": str, "url": str}
        """
        from pathlib import Path
        clean_title = re.sub(r'[\\/*?:"<>|]', "", series_title).strip() or "Series"
        filename = f"{clean_title}_S{season_num:02d}_BingePlaylist.m3u"
        target_dir = Path(output_dir) if output_dir else Path.home() / ".ripper" / "playlists"
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename

        lines = ["#EXTM3U", f"#PLAYLIST:{clean_title} Season {season_num}"]
        for ep in sorted(episodes, key=lambda x: x.get("episode", 0)):
            ep_num = ep.get("episode", 1)
            title = ep.get("title", f"{clean_title} S{season_num:02d}E{ep_num:02d}")
            url = ep.get("url", "")
            if url:
                lines.append(f"#EXTINF:-1,{title}")
                lines.append(url)

        file_path.write_text("\n".join(lines), encoding="utf-8")
        return str(file_path)

