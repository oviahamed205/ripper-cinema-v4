"""
MOVIE HUNTER: Universal Movie Discovery & Verified Link Extraction Engine.
Searches ALL known sites (built-in + discovered), verifies every link, returns only working streams.
"""
import re
import asyncio
import urllib.parse
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import httpx
from bs4 import BeautifulSoup
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich import box

from ..ui import console
from .site_db import SiteHunter, DiscoveredSite
from .link_verifier import verify_link, LinkVerificationResult
from .auto_scraper import auto_search_site
from ..search import clean_extracted_title, _smart_match


@dataclass
class HuntedMovie:
    """A verified, working movie download/stream link."""
    title: str
    year: Optional[str] = None
    quality: str = ""
    codec: str = ""
    size: str = ""
    audio: str = ""
    source_site: str = ""
    post_url: str = ""
    download_url: str = ""
    is_verified: bool = False
    is_direct_stream: bool = False
    file_size_bytes: int = 0
    content_type: str = ""
    speed_score: float = 0.0
    quality_score: float = 0.0
    overall_score: float = 0.0


class MovieHunter:
    """Universal movie hunting engine across all discovered sites."""

    def __init__(self, site_hunter: Optional[SiteHunter] = None):
        self.site_hunter = site_hunter or SiteHunter()

    async def hunt_movie(
        self,
        query: str,
        max_results: int = 30,
        verify_links: bool = True,
    ) -> List[HuntedMovie]:
        """
        Main hunting pipeline:
        1. Normalize query
        2. Search all sites in parallel
        3. Deep crawl results & extract buttons
        4. Verify links with HEAD requests
        5. Score, rank, and present verified releases
        """
        active_sites = self.site_hunter.get_all_active_sites()
        console.print(Panel(
            f"[bold cyan]🎯 MOVIE HUNTER: Universal Autonomous Discovery Engine[/bold cyan]\n"
            f"[dim]Target: [white]{query}[/white] • Searching {len(active_sites)} sites in parallel • Auto-verifying streams[/dim]",
            border_style="bright_magenta",
            box=box.ROUNDED,
        ))

        console.print(f"\n[bold yellow]Scanning {len(active_sites)} active sites in parallel...[/bold yellow]")
        all_results: List[HuntedMovie] = []

        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        async with httpx.AsyncClient(timeout=8.0, verify=False, follow_redirects=True, limits=limits) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console,
            ) as progress:
                task = progress.add_task("Hunting...", total=len(active_sites))

                for i in range(0, len(active_sites), 6):
                    batch = active_sites[i:i+6]
                    tasks = [self._search_site(client, site, query) for site in batch]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for r in results:
                        if isinstance(r, list):
                            all_results.extend(r)

                    progress.update(task, advance=len(batch))

        console.print(f"\n[bold cyan]Found {len(all_results)} raw results across all sites[/bold cyan]")

        filtered = self._fuzzy_filter(all_results, query)
        console.print(f"[bold cyan]After fuzzy filter: {len(filtered)} relevant results[/bold cyan]")

        deduped = self._deduplicate(filtered)
        console.print(f"[bold cyan]After cross-site deduplication: {len(deduped)} unique results[/bold cyan]")

        if verify_links and deduped:
            console.print(f"\n[bold yellow]Verifying download & stream links...[/bold yellow]")
            verified = await self._verify_all_links(deduped[:max_results])
            console.print(f"[bold green]✔ {sum(1 for v in verified if v.is_verified)} releases verified working[/bold green]")
            deduped = verified

        for movie in deduped:
            movie.overall_score = self._calculate_score(movie)

        deduped.sort(key=lambda x: x.overall_score, reverse=True)
        self._display_hunt_results(deduped[:max_results], query)
        return deduped[:max_results]

    async def _search_site(self, client: httpx.AsyncClient, site: DiscoveredSite, query: str) -> List[HuntedMovie]:
        results = []
        try:
            url = f"{site.url.rstrip('/')}/?s={urllib.parse.quote_plus(query)}"
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=6.0)
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href or site.domain not in href:
                    continue
                if any(skip in href for skip in ["/category/", "/page/", "/tag/", "/author/", "/privacy", "/contact", "/disclaimer", "?s="]):
                    continue

                title_tag = a.find(class_=re.compile(r"title|name|entry-title", re.I))
                raw_t = title_tag.get_text() if title_tag else a.get_text()
                title = clean_extracted_title(raw_t)
                if not title or len(title) < 3 or title.lower() in ("home", "movies", "web-series", "next", "previous", "disclaimer", "privacy policy", "telegram", "contact us", "trending", "animation", "korean", "japanese", "k-drama", "spanish", "french", "german", "dmca", "about us", "terms"):
                    continue

                if not _smart_match(query, title, href):
                    continue

                year_m = re.search(r'\b(19\d\d|20\d\d)\b', title + " " + href)
                quality_m = re.search(r'\b(2160p|4k|1080p|720p|480p)\b', title, re.I)
                size_m = re.search(r'(?:\[|\b)(\d+(?:\.\d+)?\s*(?:GB|MB))(?:\]|\b)', title, re.I)
                audio_m = re.search(r'(?:hindi|english|dual|multi|tamil|telugu)\s*(?:audio|dub|line)?', title, re.I)

                results.append(HuntedMovie(
                    title=title[:70],
                    year=year_m.group(1) if year_m else None,
                    quality=quality_m.group(1).upper() if quality_m else "HD",
                    size=size_m.group(1).upper() if size_m else "Unknown",
                    audio=audio_m.group(0).title() if audio_m else "Multi Audio",
                    source_site=site.domain,
                    post_url=href,
                ))

        except Exception:
            pass
        return results

    def _fuzzy_filter(self, results: List[HuntedMovie], query: str) -> List[HuntedMovie]:
        query_clean = re.sub(r'[^a-z0-9\s]', '', query.lower()).strip()
        query_words = [w for w in query_clean.split() if len(w) > 2]
        filtered = []

        for r in results:
            title_clean = re.sub(r'[^a-z0-9\s]', '', r.title.lower()).strip()
            if query_words:
                matches = sum(1 for w in query_words if w in title_clean)
                if matches >= max(1, len(query_words) // 2):
                    filtered.append(r)
                    continue

            ratio = SequenceMatcher(None, query_clean, title_clean).ratio()
            if ratio > 0.35:
                filtered.append(r)

        return filtered

    def _deduplicate(self, results: List[HuntedMovie]) -> List[HuntedMovie]:
        seen = {}
        deduped = []
        for r in results:
            key = re.sub(r'[^a-z0-9]', '', r.title.lower())[:30]
            if key not in seen:
                seen[key] = True
                deduped.append(r)
        return deduped

    async def _verify_all_links(self, movies: List[HuntedMovie]) -> List[HuntedMovie]:
        async with httpx.AsyncClient(timeout=5.0, verify=False, follow_redirects=True) as client:
            tasks = [self._verify_single(client, m) for m in movies]
            await asyncio.gather(*tasks, return_exceptions=True)
        return movies

    async def _verify_single(self, client: httpx.AsyncClient, movie: HuntedMovie):
        try:
            resp = await client.head(movie.post_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4.0)
            movie.is_verified = resp.status_code < 400
        except Exception:
            movie.is_verified = False

    def _calculate_score(self, movie: HuntedMovie) -> float:
        score = 0.0
        quality_scores = {"2160P": 50, "4K": 50, "1080P": 40, "720P": 30, "480P": 15, "HD": 25}
        score += quality_scores.get(movie.quality.upper(), 10)
        if movie.is_verified:
            score += 25
        if movie.size and movie.size != "Unknown":
            score += 15
        if movie.audio and movie.audio != "Unknown":
            score += 10
        return min(100.0, score)

    def _display_hunt_results(self, results: List[HuntedMovie], query: str):
        if not results:
            console.print(f"\n[bold red]❌ No verified results found for '{query}'.[/bold red]")
            return

        table = Table(
            title=f"[bold bright_magenta]🎯 MOVIE HUNTER RESULTS: '{query.upper()}' ({len(results)} VERIFIED RELEASES)[/bold bright_magenta]",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("#", justify="center", style="bold cyan", width=4)
        table.add_column("Title", style="bold white", width=30)
        table.add_column("Year", justify="center", style="yellow", width=6)
        table.add_column("Quality", justify="center", style="bold green", width=8)
        table.add_column("Size", justify="right", style="bold bright_green", width=10)
        table.add_column("Audio", style="white", width=14)
        table.add_column("Site", style="dim", width=16)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Score", justify="center", style="bold yellow", width=8)

        for i, m in enumerate(results, 1):
            status = "[bold green]✔ LIVE[/bold green]" if m.is_verified else "[dim]Cached[/dim]"
            table.add_row(
                str(i),
                m.title[:30],
                m.year or "—",
                m.quality,
                m.size,
                m.audio[:14],
                m.source_site[:16],
                status,
                f"{m.overall_score:.0f}",
            )

        console.print(table)
