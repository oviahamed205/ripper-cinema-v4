"""
YouTube Trailer Search & Browser Viewer for unshorten-cli.
Searches trailers via YouTube Data API v3 or direct YouTube link and opens in browser.
"""

import urllib.parse
import webbrowser
import httpx
from typing import Dict, Any, Optional
from .config import get_config_value

YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"


async def find_trailer(
    title: str,
    year: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 4.0,
) -> Dict[str, Any]:
    """
    Find official trailer for a movie or TV show.
    Uses YouTube Data API if available, otherwise generates a resolvable direct search URL.
    """
    key = api_key or get_config_value("youtube_api_key", "")
    query_str = f"{title} {year or ''} official trailer".strip()

    if key:
        try:
            params = {
                "key": key,
                "q": query_str,
                "part": "snippet",
                "maxResults": 1,
                "type": "video",
            }
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                resp = await client.get(YOUTUBE_SEARCH_API, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    if items:
                        vid = items[0].get("id", {}).get("videoId")
                        if vid:
                            return {
                                "trailer_url": f"https://www.youtube.com/watch?v={vid}",
                                "title": items[0].get("snippet", {}).get("title"),
                                "source": "YouTube Data API",
                            }
        except Exception:
            pass

    # Direct YouTube Search Link (No API key required)
    encoded_q = urllib.parse.quote_plus(query_str)
    return {
        "trailer_url": f"https://www.youtube.com/results?search_query={encoded_q}",
        "title": f"{title} Official Trailer",
        "source": "YouTube Search",
    }


def open_trailer_in_browser(trailer_url: str) -> bool:
    """Open trailer URL in user's default web browser."""
    try:
        webbrowser.open(trailer_url, new=2)
        return True
    except Exception:
        return False
