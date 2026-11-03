"""
Metadata API Brain Layer for unshorten-cli.
Integrates 3 free metadata providers to power title normalization, year confirmation,
poster/thumbnail art, episode counts, and "Did you mean" suggestions:
1. TMDB (TheMovieDB) - Primary Brain for Movies & TV (with API key in ~/.ripper/config.json)
2. TVmaze - Free TV Series Brain (No key required, unlimited)
3. AniList - Free Anime Brain via GraphQL (No key required, unlimited)
"""

import asyncio
from typing import List, Dict, Any, Optional
import httpx

from .config import get_config_value, load_config
from .cache import GLOBAL_CACHE

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TVMAZE_BASE_URL = "https://api.tvmaze.com"
ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"


async def search_tmdb(
    query: str,
    api_key: Optional[str] = None,
    read_token: Optional[str] = None,
    timeout: float = 4.0,
) -> List[Dict[str, Any]]:
    """Query TMDB multi-search endpoint for movie and TV metadata using Read Access Token or API Key."""
    token = read_token or get_config_value("tmdb_read_access_token", "")
    key = api_key or get_config_value("tmdb_api_key", "")
    if not token and not key:
        return []

    results = []
    try:
        url = f"{TMDB_BASE_URL}/search/multi"
        params = {"query": query, "include_adult": "false"}
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif key:
            params["api_key"] = key

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                return []

            data = resp.json()
            for item in data.get("results", []):
                media_type = item.get("media_type")
                if media_type not in ("movie", "tv"):
                    continue

                raw_title = item.get("title") if media_type == "movie" else item.get("name")
                date_str = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
                year = date_str[:4] if date_str and len(date_str) >= 4 else None

                poster_path = item.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
                backdrop_path = item.get("backdrop_path")
                backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None

                results.append({
                    "canonical_title": raw_title,
                    "year": year,
                    "media_type": "Movie" if media_type == "movie" else "TV Series",
                    "rating": round(float(item.get("vote_average", 0)), 1),
                    "overview": item.get("overview", ""),
                    "poster_url": poster_url,
                    "backdrop_url": backdrop_url,
                    "source_api": "TMDB",
                    "tmdb_id": item.get("id"),
                    "popularity": float(item.get("popularity", 0)),
                })
    except Exception:
        pass
    return results


async def search_tvmaze(query: str, timeout: float = 4.0) -> List[Dict[str, Any]]:
    """Query TVmaze search endpoint for structured TV series metadata (No API key needed)."""
    results = []
    try:
        url = f"{TVMAZE_BASE_URL}/search/shows"
        params = {"q": query}
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []

            for entry in resp.json():
                show = entry.get("show", {})
                if not show:
                    continue

                name = show.get("name", "")
                premiered = show.get("premiered", "")
                year = premiered[:4] if premiered and len(premiered) >= 4 else None

                img = show.get("image") or {}
                poster_url = img.get("medium") or img.get("original")

                rating_obj = show.get("rating") or {}
                rating = float(rating_obj.get("average")) if rating_obj.get("average") else None

                genres = ", ".join(show.get("genres", []))

                results.append({
                    "canonical_title": name,
                    "year": year,
                    "media_type": "TV Series",
                    "rating": rating or 0.0,
                    "genres": genres,
                    "poster_url": poster_url,
                    "source_api": "TVmaze",
                    "tvmaze_id": show.get("id"),
                    "status": show.get("status", ""),
                    "popularity": (rating or 5.0) * 10.0,
                })
    except Exception:
        pass
    return results


async def search_anilist(query: str, timeout: float = 4.0) -> List[Dict[str, Any]]:
    """Query AniList GraphQL API for anime metadata (No API key needed)."""
    results = []
    gql_query = """
    query ($q: String) {
      Page(perPage: 5) {
        media(search: $q, type: ANIME, sort: POPULARITY_DESC) {
          id
          title {
            romaji
            english
            native
          }
          startDate {
            year
          }
          episodes
          format
          averageScore
          genres
          bannerImage
          coverImage {
            medium
            large
          }
        }
      }
    }
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.post(
                ANILIST_GRAPHQL_URL,
                json={"query": gql_query, "variables": {"q": query}},
                headers={"Content-Type": "application/json", "Accept": "application/json"}
            )
            if resp.status_code != 200:
                return []

            data = resp.json().get("data", {}).get("Page", {}).get("media", [])
            for item in data:
                titles = item.get("title") or {}
                canonical_t = titles.get("english") or titles.get("romaji") or titles.get("native")
                if not canonical_t:
                    continue

                year_val = item.get("startDate", {}).get("year")
                year = str(year_val) if year_val else None

                score_100 = item.get("averageScore")
                rating = round(score_100 / 10.0, 1) if score_100 else 0.0

                img_obj = item.get("coverImage") or {}
                poster_url = img_obj.get("large") or img_obj.get("medium")

                episodes = item.get("episodes")
                genres = ", ".join(item.get("genres", [])[:3])

                results.append({
                    "canonical_title": canonical_t,
                    "year": year,
                    "media_type": "Anime" if item.get("format") != "MOVIE" else "Anime Movie",
                    "rating": rating,
                    "genres": genres,
                    "poster_url": poster_url,
                    "backdrop_url": item.get("bannerImage"),
                    "source_api": "AniList",
                    "anilist_id": item.get("id"),
                    "episodes": episodes,
                    "popularity": (score_100 or 50.0),
                })
    except Exception:
        pass
    return results


async def unified_metadata_search(query: str, tmdb_key: Optional[str] = None, timeout: float = 4.0) -> List[Dict[str, Any]]:
    """
    Query TMDB, TVmaze, and AniList in parallel.
    Returns normalized, deduplicated list of candidate title matches.
    """
    cfg = load_config()
    if not cfg.get("use_apis", True):
        return []

    effective_tmdb_key = tmdb_key or cfg.get("tmdb_api_key", "")

    tasks = [
        search_tvmaze(query, timeout=timeout),
        search_anilist(query, timeout=timeout),
    ]
    if effective_tmdb_key:
        tasks.append(search_tmdb(query, api_key=effective_tmdb_key, timeout=timeout))

    results_sets = await asyncio.gather(*tasks, return_exceptions=True)

    combined: List[Dict[str, Any]] = []
    for r in results_sets:
        if isinstance(r, list):
            combined.extend(r)

    seen = set()
    deduped: List[Dict[str, Any]] = []

    combined.sort(key=lambda x: x.get("popularity", 0), reverse=True)

    for item in combined:
        t = item.get("canonical_title", "").lower().strip()
        y = item.get("year") or ""
        k = (t, y)
        if k not in seen:
            seen.add(k)
            deduped.append(item)

    return deduped[:8]


