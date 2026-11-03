"""
OMDb API Integration for unshorten-cli.
Fetches IMDB ratings, Rotten Tomatoes, Awards, Cast, and Plot summaries.
"""

import httpx
from typing import Dict, Any, Optional
from .config import get_config_value

OMDB_BASE_URL = "http://www.omdbapi.com/"


async def fetch_omdb_details(
    title: str,
    year: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 4.0,
) -> Dict[str, Any]:
    """Fetch IMDb, Rotten Tomatoes, Metacritic, and Awards from OMDb."""
    key = api_key or get_config_value("omdb_api_key", "")
    if not key:
        return {}

    result = {}
    try:
        params = {"apikey": key, "t": title, "plot": "short"}
        if year:
            params["y"] = year

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(OMDB_BASE_URL, params=params)
            if resp.status_code != 200:
                return {}

            data = resp.json()
            if data.get("Response") == "False":
                return {}


            ratings = {rat.get("Source"): rat.get("Value") for rat in data.get("Ratings", []) if "Source" in rat}

            result = {
                "imdb_rating": data.get("imdbRating"),
                "rotten_tomatoes": ratings.get("Rotten Tomatoes"),
                "metacritic": ratings.get("Metacritic"),
                "awards": data.get("Awards"),
                "cast": data.get("Actors"),
                "director": data.get("Director"),
                "genre": data.get("Genre"),
                "box_office": data.get("BoxOffice"),
                "plot": data.get("Plot"),
            }
    except Exception:
        pass
    return result
