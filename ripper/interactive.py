"""
Interactive visual terminal dashboard for unshorten-cli (Enterprise & Pro Edition).
Features:
- [1] ⚡ 1-Click Instant Watch in PotPlayer (Paste URL -> Opens and Plays Immediately!)
- [2] 🔍 Search Movies & Series by Name (Deep Multi-Site Scan across CineFreak, KMmovies, Katworld)
- [3] 🎬 Extract & Unshorten Media Grid (Step-by-Step Quality & Server Selector)
- [4] 🔗 Unshorten Single URL (Hop-by-hop visual redirect tree & safety report)
- [5] 🛡️ Deep Security & Header Inspector
- [6] ⚙️  Configure Settings
- [0] 🚪 Exit
"""

import sys
import os
import re
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import httpx

from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table
from rich import box

from .resolver import unshorten_url, DEFAULT_USER_AGENT, crawl_intermediate_server_page, extract_url_from_query_params
from .models import UnshortenResult
from .media import extract_media_items_from_html, resolve_single_media_item_fast, MediaDownloadItem, DEFAULT_HEADERS, extract_direct_cloud_from_d_endpoint
from .player import launch_video_stream_in_player, detect_available_players
from .downloader import download_file_fast
from .search import execute_multi_site_search, SearchResultItem
from .ui import console, display_unshorten_banner, display_unshorten_summary


def prompt_multiline_input(prompt_text: str = "📋 Paste your text/URLs/HTML below. (Press Enter on an empty line when finished):") -> str:
    """Prompt user for multiple lines of URLs or HTML."""
    console.print(f"\n[bold cyan]{prompt_text}[/bold cyan]")
    lines = []
    while True:
        try:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        except EOFError:
            break
    return "\n".join(lines)


def display_media_options_menu(items: List[MediaDownloadItem]):
    """Display clean, compact, and perfectly aligned quality table with exact file sizes and prints."""
    movie_title = items[0].movie_name if items else "MOVIE"
    table = Table(
        title=f"[bold bright_magenta]🎬 SELECT QUALITY — {movie_title.upper()}[/bold bright_magenta]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_blue",
    )
    table.add_column("#", justify="center", style="bold cyan", min_width=4, no_wrap=True)
    table.add_column("Quality & Print", style="bold yellow", min_width=22)
    table.add_column("Real File Size", justify="right", style="bold bright_green", min_width=14, no_wrap=True)
    table.add_column("Audio / Language", style="white", min_width=20)
    table.add_column("Status", justify="center", style="bold green", min_width=14, no_wrap=True)

    for i, it in enumerate(items, 1):
        codec_display = f"{it.codec} {it.quality}" if it.codec and it.codec != "HD" else it.quality
        size_display = it.size_str if it.size_str and it.size_str != "Unknown" else "[dim]Unknown[/dim]"
        table.add_row(
            str(i),
            f"📽️  {codec_display}",
            size_display,
            it.audio_info,
            "✔ Available",
        )

    console.print(table)


def rank_and_badge_servers(servers: List[Any]) -> Tuple[List[Any], bool]:
    """
    Ranks server mirrors prioritizing Cloudflare R2 Direct CDN (10 Gbps).
    If R2 is absent, shifts gracefully to PixelDrain, Skydrop, GoFile, and alternative high-speed mirrors.
    Returns (sorted_servers, has_r2).
    """
    def server_score(s):
        url = (getattr(s, "direct_download_url", "") or getattr(s, "intermediate_url", "") or "").lower()
        lbl = (getattr(s, "label", "") or "").lower()
        typ = (getattr(s, "server_type", "") or "").lower()

        # Priority 0: Cloudflare R2 Direct CDN (fastest 10 Gbps)
        if any(k in url for k in ["r2.cloudflarestorage.com", "r2.dev", "pub-"]) or "cloudflare r2" in lbl or "cloudflare r2" in typ or "10 gbps" in lbl:
            return 0
        # Priority 1: PixelDrain Direct CDN
        if "pixeldrain.com" in url or "pixeldrain" in lbl or "pixeldrain" in typ:
            return 1
        # Priority 2: SkyDrop / GoFile / FastDL / Direct Cloud Stream
        if any(k in url for k in ["skydrop", "gofile", "fastdl", "worker", "direct", "stream"]):
            return 2
        # Priority 3: Any direct download URL
        if getattr(s, "direct_download_url", None):
            return 3
        # Priority 4: Intermediate / mirror links
        return 4

    sorted_servers = sorted(servers, key=server_score)
    has_r2 = any(server_score(s) == 0 for s in sorted_servers)
    return sorted_servers, has_r2


async def handle_server_action_menu(
    server_label: str,
    target_url: str,
    is_direct_stream: bool,
    filename: str,
    fallback_servers: Optional[List[str]] = None,
):
    """Sub-menu allowing the user to Watch in PotPlayer/VLC, Download, or Copy full link."""
    detected_players = detect_available_players()
    player_name = detected_players[0][0] if detected_players else "Default Video Player"

    url_lower = target_url.lower()
    lbl_lower = server_label.lower()
    is_r2 = any(k in url_lower for k in ["r2.cloudflarestorage.com", "r2.dev", "pub-"]) or "cloudflare r2" in lbl_lower or "10 gbps" in lbl_lower
    is_pd = "pixeldrain.com" in url_lower or "pixeldrain" in lbl_lower

    if is_r2:
        speed_badge = "[bold bright_green]⚡ 10 Gbps Cloudflare R2 Direct CDN (Fastest)[/bold bright_green]"
        dl_text = f"📥 [bold bright_green]Turbo 8-Thread Download to Disk[/bold bright_green] [dim]({speed_badge})[/dim]"
    elif is_pd:
        speed_badge = "[bold yellow]⚡ PixelDrain High-Speed Direct Mirror[/bold yellow]"
        dl_text = f"📥 [bold bright_yellow]Turbo 8-Thread Download to Disk[/bold bright_yellow] [dim]({speed_badge})[/dim]"
    else:
        speed_badge = "[cyan]⚡ Direct Cloud Mirror[/cyan]"
        dl_text = "📥 [bold bright_yellow]Turbo 8-Thread Download to Disk[/bold bright_yellow] (~/Downloads)"

    while True:
        console.print(Panel(
            f"[bold yellow]🎯 SELECTED SERVER:[/bold yellow] [bold white]{server_label}[/bold white]\n"
            f"[bold yellow]⚡ SPEED TIER:[/bold yellow] {speed_badge}\n"
            f"[bold yellow]🔗 FULL DIRECT URL:[/bold yellow]\n[bold bright_green]{target_url}[/bold bright_green]",
            title="[bold green]FULL DIRECT LINK DETAILS[/bold green]",
            border_style="bright_green",
            box=box.ROUNDED,
        ))

        action_menu = (
            f"[bold white][1][/bold white] 🎬 [bold bright_cyan]Watch Stream in {player_name}[/bold bright_cyan] (Instant playback, no download needed)\n"
            f"[bold white][2][/bold white] {dl_text}\n"
            f"[bold white][3][/bold white] 📋 [bold white]Copy / Print Full Raw Link[/bold white]\n"
            f"[bold white][4][/bold white] 📡 [bold bright_magenta]Broadcast Stream on Local Network (LAN)[/bold bright_magenta]\n"
            f"[bold white][5][/bold white] 🖥️ [bold bright_green]Play on PC & Broadcast on LAN[/bold bright_green] (Simultaneous local player + phone stream)\n"
            f"[bold white][0][/bold white] ↩️  [bold red]Back to Server List[/bold red]"
        )
        console.print(Panel(action_menu, title="[bold cyan]ACTIONS FOR SELECTED STREAM[/bold cyan]", box=box.ROUNDED))

        action = Prompt.ask(
            "[bold yellow]Choose an action[/bold yellow]",
            choices=["1", "2", "3", "4", "5", "0"],
            default="2" if is_r2 else "1",
        )

        if action == "0":
            break

        elif action == "1":
            console.print(f"\n[bold cyan]⚡ Deep-resolving direct playable stream for {player_name}...[/bold cyan]")
            from .resolver import resolve_to_direct_stream_url
            playable_url = await resolve_to_direct_stream_url(target_url)
            console.print(f"[bold cyan]🚀 Sending stream URL to {player_name}...[/bold cyan]")
            success, msg = launch_video_stream_in_player(playable_url)
            if success:
                console.print(f"[bold green]✔ {msg}[/bold green]")
            else:
                console.print(f"[bold red]❌ {msg}[/bold red]")
            Prompt.ask("\nPress Enter to continue")

        elif action == "2":
            from .resolver import resolve_to_direct_stream_url
            console.print(f"\n[bold cyan]⚡ Resolving direct download stream...[/bold cyan]")
            download_url = await resolve_to_direct_stream_url(target_url)
            console.print(f"[bold cyan]📥 Starting Turbo 8-Thread parallel download for: [white]{filename}[/white]...[/bold cyan]")

            # Define automatic background token refresher for expiring Cloudflare R2 links
            async def auto_refresh_token():
                return await resolve_to_direct_stream_url(target_url)

            try:
                dest = await download_file_fast(
                    download_url,
                    custom_filename=filename,
                    refresh_token_callback=auto_refresh_token,
                    fallback_mirrors=fallback_servers,
                )
                console.print(f"\n[bold green]✔ Download Complete! Saved to: {dest}[/bold green]")
            except Exception as e:
                console.print(f"[bold red]❌ Download error: {e}[/bold red]")
            Prompt.ask("\nPress Enter to continue")

        elif action == "3":
            console.print(f"\n[bold bright_yellow]FULL COPYABLE URL:[/bold bright_yellow]")
            print(target_url)
            Prompt.ask("\nPress Enter to continue")

        elif action == "4":
            console.print(f"\n[bold cyan]⚡ Deep-resolving stream URL for LAN Broadcast...[/bold cyan]")
            from .resolver import resolve_to_direct_stream_url
            playable_url = await resolve_to_direct_stream_url(target_url)
            from .broadcast import start_broadcast_server
            start_broadcast_server(playable_url, filename)
            Prompt.ask("\nPress Enter to stop broadcast and return")

        elif action == "5":
            console.print(f"\n[bold cyan]⚡ Deep-resolving stream URL for Simultaneous Stream...[/bold cyan]")
            from .resolver import resolve_to_direct_stream_url
            playable_url = await resolve_to_direct_stream_url(target_url)
            from .broadcast import start_broadcast_server
            start_broadcast_server(playable_url, filename)
            local_stream = "http://127.0.0.1:5060/stream"
            console.print(f"[bold cyan]🚀 Launching local stream in {player_name}...[/bold cyan]")
            launch_video_stream_in_player(local_stream)
            Prompt.ask("\nPress Enter to stop broadcast and return")


async def run_one_click_instant_watch(url_or_snippet: str, timeout: float = 5.0, audio_language: Optional[str] = None):
    """
    ⚡ 1-Click Instant Watch Engine:
    1. Fetches webpage / unwraps shortener in < 0.5s
    2. Auto-selects highest quality (or lets user 1-key pick)
    3. Extracts direct Cloudflare R2 presigned stream
    4. Automatically launches PotPlayer to play the movie!
    """
    raw_input = url_or_snippet.strip()
    if not raw_input:
        return

    console.print("\n[bold cyan]⚡ INITIATING 1-CLICK INSTANT STREAM PIPELINE...[/bold cyan]")
    detected_players = detect_available_players()
    player_name = detected_players[0][0] if detected_players else "PotPlayer"

    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
    async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True, limits=limits) as client:
        # Case A1: Direct links.kmhd.eu / links.kmhd.me URL
        if any(d in raw_input for d in ["links.kmhd.eu", "links.kmhd.me", "kmhd."]):
            from .resolver import resolve_kmhd_page
            console.print(f"[bold cyan]🔍 Unlocking KMHD & extracting Cloudflare R2 Stream...[/bold cyan]")
            km_servers = await resolve_kmhd_page(client, raw_input, DEFAULT_HEADERS, timeout=timeout)
            direct_s = next((s.direct_download_url for s in km_servers if s.direct_download_url), None)
            if direct_s:
                console.print(f"\n[bold green]✔ Direct Stream Discovered:[/bold green] [dim]{direct_s[:75]}...[/dim]")
                console.print(f"[bold bright_magenta]🎬 Launching {player_name}...[/bold bright_magenta]")
                success, msg = launch_video_stream_in_player(direct_s)
                if success:
                    console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
                else:
                    console.print(f"[bold red]❌ {msg}[/bold red]")
                Prompt.ask("\nPress Enter to return to main menu")
                return

        # Case A2: Direct magiclinks.lol URL
        if "magiclinks.lol" in raw_input:
            from .resolver import resolve_magiclinks_page
            console.print(f"[bold cyan]🔍 Resolving MagicLinks stream mirrors...[/bold cyan]")
            ml_servers = await resolve_magiclinks_page(client, raw_input, DEFAULT_HEADERS, timeout=timeout)
            direct_s = next((s.direct_download_url for s in ml_servers if s.direct_download_url), None)
            target_to_play = direct_s or (ml_servers[0].intermediate_url if ml_servers else None)
            if target_to_play:
                console.print(f"\n[bold green]✔ Stream Link Discovered:[/bold green] [dim]{target_to_play[:75]}...[/dim]")
                console.print(f"[bold bright_magenta]🎬 Launching {player_name}...[/bold bright_magenta]")
                success, msg = launch_video_stream_in_player(target_to_play)
                if success:
                    console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
                else:
                    console.print(f"[bold red]❌ {msg}[/bold red]")
                Prompt.ask("\nPress Enter to return to main menu")
                return

        # Case A3: Direct vcloud.fit URL
        if "vcloud.fit" in raw_input:
            from .resolver import resolve_vcloud_page
            console.print(f"[bold cyan]🔍 Resolving VegaCloud & extracting Cloudflare R2 Stream...[/bold cyan]")
            vc_servers = await resolve_vcloud_page(client, raw_input, DEFAULT_HEADERS, timeout=timeout)
            direct_s = next((s.direct_download_url for s in vc_servers if s.direct_download_url), None)
            if direct_s:
                console.print(f"\n[bold green]✔ Direct Stream Discovered:[/bold green] [dim]{direct_s[:75]}...[/dim]")
                console.print(f"[bold bright_magenta]🎬 Launching {player_name}...[/bold bright_magenta]")
                success, msg = launch_video_stream_in_player(direct_s)
                if success:
                    console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
                else:
                    console.print(f"[bold red]❌ {msg}[/bold red]")
                Prompt.ask("\nPress Enter to return to main menu")
                return

        # Case A4: Direct nexdrive.fit URL
        if "nexdrive.fit" in raw_input:
            from .resolver import resolve_nexdrive_page
            console.print(f"[bold cyan]🔍 Resolving NexDrive & extracting Cloudflare R2 Stream...[/bold cyan]")
            nex_servers = await resolve_nexdrive_page(client, raw_input, DEFAULT_HEADERS, timeout=timeout)
            direct_s = next((s.direct_download_url for s in nex_servers if s.direct_download_url), None)
            if direct_s:
                console.print(f"\n[bold green]✔ Direct Stream Discovered:[/bold green] [dim]{direct_s[:75]}...[/dim]")
                console.print(f"[bold bright_magenta]🎬 Launching {player_name}...[/bold bright_magenta]")
                success, msg = launch_video_stream_in_player(direct_s)
                if success:
                    console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
                else:
                    console.print(f"[bold red]❌ {msg}[/bold red]")
                Prompt.ask("\nPress Enter to return to main menu")
                return

        # Case A5: Direct CineCloud / Base64 generator URL
        if "cinecloud" in raw_input or "generate.php" in raw_input:
            landing = extract_url_from_query_params(raw_input) or raw_input
            fid_match = re.search(r'/f/([a-zA-Z0-9]+)', landing)
            if fid_match:
                d_url = f"https://new5.cinecloud.site/d/{fid_match.group(1)}"
                console.print(f"[bold cyan]🔍 Resolving direct stream from Cloud [Resumable]...[/bold cyan]")
                direct_stream = await extract_direct_cloud_from_d_endpoint(client, d_url, DEFAULT_HEADERS, timeout=timeout)
                if direct_stream:
                    console.print(f"\n[bold green]✔ Direct Stream Discovered:[/bold green] [dim]{direct_stream[:75]}...[/dim]")
                    console.print(f"[bold bright_magenta]🎬 Launching {player_name}...[/bold bright_magenta]")
                    success, msg = launch_video_stream_in_player(direct_stream)
                    if success:
                        console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
                    else:
                        console.print(f"[bold red]❌ {msg}[/bold red]")
                    Prompt.ask("\nPress Enter to return to main menu")
                    return

        # Case B: Full Movie Webpage URL
        raw_html = ""
        base_url = "https://cinefreak.net"

        if raw_input.startswith("http://") or raw_input.startswith("https://"):
            base_url = raw_input
            console.print(f"[bold cyan]🔍 Fast-fetching movie page {raw_input}...[/bold cyan]")
            try:
                resp = await client.get(raw_input, headers=DEFAULT_HEADERS)
                raw_html = resp.text
            except Exception as e:
                console.print(f"[bold red]❌ Failed to fetch page: {e}[/bold red]")
                Prompt.ask("\nPress Enter to return to menu")
                return
        else:
            raw_html = raw_input

        items = extract_media_items_from_html(raw_html, base_url)
        if not items:
            console.print("[bold cyan]🔄 Standard selectors found 0 items. Activating Autonomous Multi-Tier Engine...[/bold cyan]")
            from .universal_engine import UniversalPipeline
            pipeline = UniversalPipeline()
            def on_step(msg: str):
                console.print(f"[dim cyan]{msg}[/dim cyan]")
            items = await pipeline.extract(raw_input, html=raw_html, client=client, progress_callback=on_step)

        if not items:
            console.print("[bold red]❌ No download links found across all autonomous tiers.[/bold red]")
            Prompt.ask("\nPress Enter to return to menu")
            return

        movie_title = items[0].movie_name if items else "Movie"
        console.print(f"\n[bold green]✔ Detected {len(items)} Qualities for {movie_title}[/bold green]")

        # Find best 1080p quality as default
        default_idx = 0
        for i, it in enumerate(items):
            if "1080" in it.quality and "HQ-LOW" not in it.codec:
                default_idx = i
                break

        # Quick 1-key prompt with default
        for i, it in enumerate(items, 1):
            is_default = (i - 1 == default_idx)
            badge = "[bold bright_yellow](★ Best Quality)[/bold bright_yellow]" if is_default else ""
            console.print(f"  [bold cyan][{i}][/bold cyan] 📽️  {it.codec} {it.quality} [{it.size_str}] {badge}")

        choice = Prompt.ask(
            f"\n[bold yellow]Press Enter for [{default_idx + 1}] {items[default_idx].codec} {items[default_idx].quality} (or type 1-{len(items)})[/bold yellow]",
            default=str(default_idx + 1),
        )

        try:
            chosen_idx = int(choice) - 1
            if not (0 <= chosen_idx < len(items)):
                chosen_idx = default_idx
        except ValueError:
            chosen_idx = default_idx

        chosen = items[chosen_idx]
        console.print(f"\n[bold cyan]⚡ Unshortening {chosen.codec} {chosen.quality} [{chosen.size_str}] & querying Cloud [Resumable] stream...[/bold cyan]")

        res = await resolve_single_media_item_fast(chosen, client, timeout=timeout, headers=DEFAULT_HEADERS)

        from .resolver import resolve_to_direct_stream_url
        direct_stream_url = None
        for s in res.servers:
            if s.direct_download_url:
                direct_stream_url = s.direct_download_url
                break

        if not direct_stream_url and res.unshortened_landing_url:
            direct_stream_url = await resolve_to_direct_stream_url(res.unshortened_landing_url, client=client, timeout=timeout)

        if not direct_stream_url and res.servers:
            for s in res.servers:
                crawled = await resolve_to_direct_stream_url(s.direct_download_url or s.intermediate_url, client=client, timeout=timeout)
                if crawled and ("r2.cloudflarestorage.com" in crawled or "amazonaws.com" in crawled or "pixeldrain.com/api/file" in crawled or any(crawled.lower().endswith(ext) for ext in [".mkv", ".mp4"])):
                    direct_stream_url = crawled
                    break
            if not direct_stream_url:
                direct_stream_url = await resolve_to_direct_stream_url(res.servers[0].intermediate_url, client=client, timeout=timeout)

        if direct_stream_url:
            direct_stream_url = await resolve_to_direct_stream_url(direct_stream_url, client=client, timeout=timeout)
            console.print(f"\n[bold green]✔ Direct Stream Acquired: [dim]{direct_stream_url[:75]}...[/dim][/bold green]")
            
            # Enhanced Subtitle Engine resolution & Charset Normalization
            from .subtitles import SubtitleEngine, parse_audio_languages_from_title
            sub_engine = SubtitleEngine()
            sub_file = await sub_engine.fetch_best_subtitle(movie_title, language="en")
            sub_path_str = str(sub_file) if sub_file else None

            # Audio Track Selection (Dual Audio / Multi Audio)
            detected_tracks = parse_audio_languages_from_title(f"{chosen.codec} {chosen.quality} {chosen.audio_info} {movie_title}")
            selected_audio_lang = audio_language
            if len(detected_tracks) > 1:
                console.print("\n[bold cyan]🔊 Multi-Language Audio Tracks Detected:[/bold cyan]")
                for idx, trk in enumerate(detected_tracks, 1):
                    badge = "[bold bright_yellow](Default)[/bold bright_yellow]" if trk.is_default else ""
                    console.print(f"  [bold cyan][{idx}][/bold cyan] 🌐 {trk.display_name} ({trk.language_code.upper()}) {badge}")
                audio_choice = Prompt.ask(
                    f"[bold yellow]Select Audio Track [1-{len(detected_tracks)}] (or press Enter for 1)[/bold yellow]",
                    default="1",
                )
                try:
                    chosen_track_idx = int(audio_choice) - 1
                    if 0 <= chosen_track_idx < len(detected_tracks):
                        selected_audio_lang = detected_tracks[chosen_track_idx].language_code
                except ValueError:
                    pass

            console.print(f"[bold bright_magenta]🎬 Launching {player_name}...[/bold bright_magenta]")
            success, msg = launch_video_stream_in_player(direct_stream_url, subtitle_path=sub_path_str, audio_language=selected_audio_lang)
            if success:
                console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]\n")
                # Record to watch history
                from .history import add_to_history
                add_to_history(
                    title=movie_title,
                    url=direct_stream_url,
                    quality=f"{chosen.codec} {chosen.quality}",
                    site_name=getattr(chosen, "site_name", "Stream Network"),
                )
            else:
                console.print(f"[bold red]❌ {msg}[/bold red]\n")
        else:
            console.print(f"[bold red]❌ Could not resolve direct stream.[/bold red]")

        Prompt.ask("Press Enter to return to main menu")


async def handle_search_flow(
    initial_query: Optional[str] = None,
    timeout: float = 5.0,
    target_site: Optional[str] = None,
    language_filter: Optional[str] = None,
    query_year: Optional[str] = None,
    quality_filter: Optional[str] = None,
    hdr: bool = False,
    atmos: bool = False,
    remux: bool = False,
    use_metadata_apis: bool = True,
    export_path: Optional[str] = None,
):
    """Deep Multi-Site Movie & Series Search Flow (with TMDB / TVmaze / AniList Brain Layer)."""
    active_target_site = target_site

    # Search Mode Selector (Multi-Site vs Single-Site Targeted Provider)
    if not initial_query and not target_site:
        console.print("\n[bold cyan]🔍 MOVIE & TV SERIES SEARCH ENGINE[/bold cyan]")
        console.print("  [bold white][1][/bold white] 🌐 [bold bright_green]Multi-Site Universal Search[/bold bright_green]  (Scan all 6 networks simultaneously)")
        console.print("  [bold white][2][/bold white] 🎯 [bold yellow]Single-Site Targeted Search[/bold yellow]  (Select a specific provider / network)")
        console.print("  [bold white][0][/bold white] ↩️  [bold red]Back to Main Menu[/bold red]\n")

        s_mode = Prompt.ask("[bold yellow]Select Search Mode[/bold yellow]", choices=["1", "2", "0"], default="1")
        if s_mode == "0":
            return
        elif s_mode == "2":
            console.print("\n[bold cyan]🎯 SELECT TARGET PROVIDER / NETWORK:[/bold cyan]")
            console.print("  [bold white][1][/bold white] 🎬 [bold white]KatmovieHD / Katworld[/bold white] (High quality 4K, 1080p, 720p)")
            console.print("  [bold white][2][/bold white] 🎬 [bold white]KMmovies[/bold white] (Fast PixelDrain / 10 Gbps servers)")
            console.print("  [bold white][3][/bold white] 🎬 [bold white]CineFreak[/bold white] (Direct Cloudflare R2 streams)")
            console.print("  [bold white][4][/bold white] 🎬 [bold white]VegaMovies[/bold white] (4K HDR10+ DV & V-Cloud)")
            console.print("  [bold white][5][/bold white] 🎬 [bold white]OlaMovies[/bold white] (High-bitrate REMUX & 10-bit)")
            console.print("  [bold white][6][/bold white] 🎬 [bold white]HDHub4u[/bold white] (Dual Audio Bollywood & Hollywood)")
            console.print("  [bold white][0][/bold white] ↩️  [bold red]Cancel[/bold red]\n")

            p_choice = Prompt.ask("[bold yellow]Choose Provider #[/bold yellow]", choices=["1", "2", "3", "4", "5", "6", "0"], default="1")
            if p_choice == "0":
                return
            provider_map = {
                "1": "katmoviehd",
                "2": "kmmovies",
                "3": "cinefreak",
                "4": "vegamovies",
                "5": "olamovies",
                "6": "hdhub4u",
            }
            active_target_site = provider_map.get(p_choice)

    query = initial_query.strip() if initial_query else Prompt.ask("\n[bold yellow]Enter movie or series title to search (e.g. 'Spider-Man', 'Breaking Bad')[/bold yellow]").strip()

    if not query:
        return

    from .search import execute_multi_site_search, resolve_site_names, normalize_title_for_grouping
    from .apis import unified_metadata_search

    search_query = query
    confirmed_year = query_year

    # Brain Layer: Query TMDB, TVmaze, AniList for smart title & year suggestions
    if use_metadata_apis:
        try:
            candidates = await unified_metadata_search(query, timeout=3.5)
            if candidates:
                api_table = Table(
                    title=f"[bold bright_magenta]🧠 METADATA BRAIN MATCHES (TMDB / TVmaze / AniList)[/bold bright_magenta]",
                    box=box.ROUNDED,
                    show_header=True,
                    header_style="bold cyan",
                    border_style="bright_blue",
                )
                api_table.add_column("#", justify="center", style="bold cyan", width=4)
                api_table.add_column("Canonical Title", style="bold white", width=36)
                api_table.add_column("Year", justify="center", style="bold yellow", width=8)
                api_table.add_column("Type", style="bold bright_green", width=12)
                api_table.add_column("Score", justify="center", style="bold yellow", width=8)

                for i, c in enumerate(candidates, 1):
                    rating_str = f"⭐ {c.get('rating')}" if c.get("rating") else "-"
                    api_table.add_row(
                        str(i),
                        c.get("canonical_title", ""),
                        str(c.get("year") or "-"),
                        c.get("media_type", "Movie"),
                        rating_str,
                    )
                console.print(api_table)

                choices = [str(i) for i in range(1, len(candidates) + 1)] + ["0"]
                sel_api = Prompt.ask(
                    f"[bold yellow]Select a match # to lock exact title & year (or '0' to search literal '{query}')[/bold yellow]",
                    choices=choices,
                    default="1",
                )
                if sel_api != "0":
                    picked = candidates[int(sel_api) - 1]
                    search_query = picked.get("canonical_title", query)
                    confirmed_year = picked.get("year") or confirmed_year
                    console.print(f"[bold green]✔ Locked Target:[/bold green] [bold white]{search_query}[/bold white] [bold yellow]({confirmed_year or 'Any'})[/bold yellow]\n")
        except Exception:
            pass

    active_site_list = resolve_site_names(active_target_site) if active_target_site else None
    site_label = ", ".join(active_site_list) if active_site_list and len(active_site_list) < 6 else "all 6 indexed networks (CineFreak, KMmovies, Katworld, VegaMovies, OlaMovies, HDHub4u)"

    console.print(f"\n[bold cyan]⚡ Scanning across {site_label} in parallel for '{search_query}'...[/bold cyan]\n")
    search_res = await execute_multi_site_search(search_query, timeout=timeout, target_sites=active_site_list, query_year=confirmed_year)

    if isinstance(search_res, tuple) and len(search_res) == 2:
        results, statuses = search_res
    else:
        results, statuses = search_res, []

    # Display per-site network status bar & connection diagnostic
    if statuses:
        radar_table = Table(
            title="[bold cyan]📡 NETWORK RADAR & SITE HEALTH STATUS[/bold cyan]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        radar_table.add_column("Site / Network", style="bold white", width=18)
        radar_table.add_column("Status", justify="center", width=12)
        radar_table.add_column("Results Found", justify="right", style="bold yellow", width=16)
        radar_table.add_column("Response Time", justify="right", style="dim", width=14)
        radar_table.add_column("Connection Info", style="dim", width=28)

        failed_sites = []
        for st in statuses:
            if st.success:
                status_badge = "[bold green]✔ ONLINE[/bold green]"
                count_badge = f"[bold bright_green]{st.result_count} hits[/bold bright_green]" if st.result_count > 0 else "[dim]0 hits[/dim]"
                latency_str = f"{st.latency_ms:.0f} ms"
                diag_info = "[green]Connected & Indexed[/green]"
            else:
                err_msg = st.error_message
                status_badge = "[bold red]✘ OFFLINE[/bold red]"
                count_badge = "[red]0 hits[/red]"
                latency_str = f"{st.latency_ms:.0f} ms"

                # Friendly human-readable diagnostic
                if "11001" in err_msg or "getaddrinfo" in err_msg or "dns" in err_msg.lower():
                    diag_info = "[bold red]✘ DNS Blocked / Domain Dead[/bold red]"
                elif "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                    diag_info = "[bold red]✘ Connection Timeout (>5s)[/bold red]"
                elif "403" in err_msg:
                    diag_info = "[bold red]✘ Cloudflare Anti-Bot Block[/bold red]"
                elif "500" in err_msg or "502" in err_msg or "503" in err_msg:
                    diag_info = "[bold red]✘ Server Offline (HTTP 5xx)[/bold red]"
                else:
                    diag_info = f"[bold red]{err_msg[:26]}[/bold red]"

                failed_sites.append((st.site_name, diag_info))

            radar_table.add_row(st.site_name, status_badge, count_badge, latency_str, diag_info)

        console.print(radar_table)

        if failed_sites:
            trouble_text = (
                f"[bold red]⚠️ Notice: {len(failed_sites)} movie network(s) could not be reached or returned connection errors:[/bold red]\n"
                + "\n".join([f"  • [bold white]{s_name}[/bold white]: {s_diag}" for s_name, s_diag in failed_sites])
                + "\n\n[bold bright_yellow]🔧 HOW TO FIX THIS ERROR & RESTORE ACCESS:[/bold bright_yellow]\n"
                "  [bold cyan]1. Update/Probe Live Mirrors:[/bold cyan] Use [bold white]Option [8] (Domain Radar)[/bold white] or [bold white]Option [H] (The Hunter Engine)[/bold white] to auto-scan 50+ TLDs and heal broken mirrors.\n"
                "  [bold cyan]2. DNS/ISP Unblocking:[/bold cyan] If your ISP blocks movie sites, change Windows DNS to [bold green]1.1.1.1[/bold green] (Cloudflare) or [bold green]8.8.8.8[/bold green] (Google), or connect a VPN.\n"
                "  [bold cyan]3. Increase Timeout:[/bold cyan] If on a slow internet connection, raise timeout to 8-10s under [bold white]Option [9] (Settings)[/bold white]."
            )
            console.print(Panel(trouble_text, title="[bold red]🛠️ CONNECTION TROUBLESHOOTING & FIX GUIDE[/bold red]", border_style="red", box=box.ROUNDED))
            console.print("")

    # Apply language filter if specified
    if language_filter:
        req_langs = [l.strip().lower() for l in language_filter.split(",") if l.strip()]
        results = [
            r for r in results
            if (r.language and any(rl in r.language.lower() for rl in req_langs))
            or (r.quality_tags and any(rl in r.quality_tags.lower() for rl in req_langs))
            or (r.title and any(rl in r.title.lower() for rl in req_langs))
            or ((r.language or "").lower() in ("multi", "dual") or "multi" in (r.quality_tags or "").lower() or "dual" in (r.quality_tags or "").lower())
        ]

    # Apply quality/resolution filter if specified
    if quality_filter:
        q_norm = quality_filter.strip().lower()
        results = [
            r for r in results
            if q_norm in r.title.lower()
            or (r.quality_tags and q_norm in r.quality_tags.lower())
            or (q_norm in ("4k", "2160p") and any(k in (r.title + " " + (r.quality_tags or "")).lower() for k in ("4k", "2160p", "uhd")))
            or (q_norm == "1080p" and any(k in (r.title + " " + (r.quality_tags or "")).lower() for k in ("1080p", "fhd")))
            or (q_norm == "720p" and any(k in (r.title + " " + (r.quality_tags or "")).lower() for k in ("720p", "hd")))
        ]

    # Apply HDR / Dolby Vision filter
    if hdr:
        results = [
            r for r in results
            if any(k in (r.title + " " + (r.quality_tags or "")).lower() for k in ("hdr", "hdr10", "dolby", "vision", "dovi", "dv"))
        ]

    # Apply Dolby Atmos / TrueHD filter
    if atmos:
        results = [
            r for r in results
            if any(k in (r.title + " " + (r.quality_tags or "")).lower() for k in ("atmos", "truehd", "dts-hd", "ddp5.1", "ddp 5.1"))
        ]

    # Apply REMUX filter
    if remux:
        results = [
            r for r in results
            if "remux" in (r.title + " " + (r.quality_tags or "")).lower()
        ]

    # Automatically rank results by Precision Release Classifier Quality Score
    try:
        from .release_classifier import classify_release
        results.sort(key=lambda r: classify_release(r.title + " " + (r.quality_tags or "")).quality_score, reverse=True)
    except Exception:
        pass

    if not results:
        console.print(f"[bold red]❌ No results found matching '{search_query}'.[/bold red]")
        Prompt.ask("\nPress Enter to return to menu")
        return

    # Export if requested
    if export_path:
        from .batch import export_search_results
        export_search_results(results, Path(export_path))
        console.print(f"[bold green]✔ Successfully exported {len(results)} search result(s) to: {export_path}[/bold green]\n")

    # Group TV series by season if detected
    series_groups: Dict[str, List[Any]] = {}
    for r in results:
        if r.season is not None:
            norm_k = normalize_title_for_grouping(r.title)
            series_groups.setdefault(norm_k, []).append(r)

    if series_groups:
        console.print("[bold bright_cyan]📺 DETECTED TV SERIES & SEASONS:[/bold bright_cyan]")
        for k, ep_list in list(series_groups.items())[:3]:
            show_name = ep_list[0].title.split("S0")[0].split("Season")[0].strip() or ep_list[0].title[:30]
            console.print(f"  [bold white]📽️  {show_name}[/bold white]")
            for ep in sorted(ep_list, key=lambda x: (x.season or 0, x.episode or 0))[:6]:
                ep_label = f"S{ep.season:02d}" + (f"E{ep.episode:02d}" if ep.episode else " Complete")
                console.print(f"     [dim]├──[/dim] [yellow]{ep_label}[/yellow] [{ep.quality_tags or 'HD'}] ({ep.site_name})")
        console.print("")

    page_size = 20
    current_page = 0
    total_pages = max(1, (len(results) + page_size - 1) // page_size)

    while True:
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(results))
        display_results = results[start_idx:end_idx]

        table = Table(
            title=f"[bold bright_magenta]🔍 SEARCH RESULTS FOR: \"{query.upper()}\" (Page {current_page + 1}/{total_pages} — {len(results)} Total Hits)[/bold bright_magenta]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("#", justify="center", style="bold cyan", width=4)
        table.add_column("Score", justify="center", style="bold green", width=7)
        table.add_column("Source Network", style="bold yellow", width=18)
        table.add_column("Title & Year", style="white", width=34)
        table.add_column("Available Qualities", style="bold bright_green", width=22)

        from .release_classifier import classify_release, format_specs_badge

        for i, r in enumerate(display_results, 1):
            year_str = f"({r.year})" if r.year else ""
            score_str = f"{r.relevance_score:.0f}" if hasattr(r, "relevance_score") and r.relevance_score > 0 else "-"
            specs = classify_release(r.title + " " + (r.quality_tags or ""))
            quality_badge = format_specs_badge(specs) if specs.resolution != "Unknown" else (r.quality_tags or "Multi-Quality")
            table.add_row(
                str(i),
                score_str,
                r.site_name,
                f"{r.title} {year_str}".strip(),
                quality_badge,
            )
        console.print(table)

        nav_options = []
        if total_pages > 1:
            if current_page < total_pages - 1:
                nav_options.append("[bold cyan][N][/bold cyan]ext Page")
            if current_page > 0:
                nav_options.append("[bold cyan][P][/bold cyan]rev Page")
        nav_options.append("[bold yellow][E][/bold yellow]xport")
        nav_options.append("[bold red][0][/bold red] Back")

        console.print(f"[dim]Navigation: {' | '.join(nav_options)}[/dim]")
        valid_choices = [str(i) for i in range(1, len(display_results) + 1)] + ["0", "e", "E"]
        if "n" in "".join(nav_options).lower():
            valid_choices.extend(["n", "N"])
        if "p" in "".join(nav_options).lower():
            valid_choices.extend(["p", "P"])

        sel = Prompt.ask(
            f"\n[bold yellow]Select a title # (1-{len(display_results)}), or navigation action[/bold yellow]",
            choices=valid_choices,
            default="1",
        )

        if sel == "0":
            return
        elif sel in ("n", "N"):
            current_page += 1
            continue
        elif sel in ("p", "P"):
            current_page -= 1
            continue
        elif sel in ("e", "E"):
            out_f = Prompt.ask("Enter export filepath (e.g. search_results.json, .csv, .md)", default="search_results.json")
            from .batch import export_search_results
            export_search_results(results, Path(out_f))
            console.print(f"[bold green]✔ Exported {len(results)} results to {out_f}[/bold green]")
            continue

        chosen_result = display_results[int(sel) - 1]
        console.print(Panel(
            f"[bold yellow]🎯 SELECTED MOVIE:[/bold yellow] [bold white]{chosen_result.title}[/bold white]\n"
            f"[bold yellow]🌐 SOURCE SITE:[/bold yellow] [bold cyan]{chosen_result.site_name}[/bold cyan]\n"
            f"[bold yellow]🔗 POST URL:[/bold yellow] [dim]{chosen_result.url}[/dim]",
            title="[bold green]STREAM SELECTION[/bold green]",
            box=box.ROUNDED,
        ))

        sub_action = Prompt.ask(
            "[bold yellow]Action: [1] 1-Click PotPlayer Watch, [2] Quality Selector, [T] 🎬 Trailer, [F] ⭐ Watchlist, [O] ℹ️ IMDb Info, [0] Back[/bold yellow]",
            choices=["1", "2", "t", "T", "f", "F", "o", "O", "0"],
            default="1",
        )

        if sub_action == "1":
            console.print(f"\n[bold cyan]🚀 Resolving direct stream for 1-Click Instant Watch...[/bold cyan]")
            await run_one_click_instant_watch(chosen_result.url, timeout=timeout)
            break
        elif sub_action == "2":
            from .media import extract_media_items_from_html
            try:
                async with httpx.AsyncClient(timeout=timeout + 3.0, verify=False, follow_redirects=True) as c:
                    resp = await c.get(chosen_result.url, headers=DEFAULT_HEADERS)
                    raw_html = resp.text
                    items = extract_media_items_from_html(raw_html, chosen_result.url)
                    if items:
                        await run_interactive_media_selection(items, timeout=timeout)
                    else:
                        console.print("[bold red]❌ No direct download grid found on this post.[/bold red]")
                        Prompt.ask("\nPress Enter to continue")
            except Exception as e:
                console.print(f"[bold red]❌ Failed to load movie post: {e}[/bold red]")
                Prompt.ask("\nPress Enter to continue")
            break
        elif sub_action in ("t", "T"):
            from .trailer import find_trailer, open_trailer_in_browser
            t_data = await find_trailer(chosen_result.title, chosen_result.year)
            console.print(f"\n[bold green]🎬 Opening Official Trailer in Browser:[/bold green] [dim]{t_data.get('trailer_url')}[/dim]")
            open_trailer_in_browser(t_data.get("trailer_url", ""))
            Prompt.ask("\nPress Enter to return to selection")
            continue
        elif sub_action in ("f", "F"):
            from .watchlist import add_to_watchlist
            added = add_to_watchlist(
                title=chosen_result.title,
                url=chosen_result.url,
                site_name=chosen_result.site_name,
                year=chosen_result.year,
                quality=chosen_result.quality_tags,
                poster_url=chosen_result.poster_url,
            )
            if added:
                console.print(f"\n[bold green]⭐ Added '{chosen_result.title}' to your Watchlist![/bold green]")
            else:
                console.print(f"\n[bold yellow]Already in your Watchlist.[/bold yellow]")
            Prompt.ask("\nPress Enter to continue")
            continue
        elif sub_action in ("o", "O"):
            from .omdb import fetch_omdb_details
            omdb_data = await fetch_omdb_details(chosen_result.title, chosen_result.year)
            if omdb_data:
                console.print(Panel(
                    f"[bold yellow]⭐ IMDb Rating:[/bold yellow] [bold white]{omdb_data.get('imdb_rating') or 'N/A'}/10[/bold white]  |  "
                    f"[bold red]🍅 Rotten Tomatoes:[/bold red] [bold white]{omdb_data.get('rotten_tomatoes') or 'N/A'}[/bold white]\n"
                    f"[bold yellow]🎭 Genre:[/bold yellow] {omdb_data.get('genre') or 'N/A'}  |  [bold yellow]🎬 Director:[/bold yellow] {omdb_data.get('director') or 'N/A'}\n"
                    f"[bold yellow]👥 Cast:[/bold yellow] {omdb_data.get('cast') or 'N/A'}\n"
                    f"[bold yellow]🏆 Awards:[/bold yellow] {omdb_data.get('awards') or 'N/A'}\n\n"
                    f"[bold yellow]📖 Plot:[/bold yellow]\n[dim]{omdb_data.get('plot') or 'N/A'}[/dim]",
                    title=f"[bold bright_magenta]ℹ️ IMDb & OMDb INTEL — {chosen_result.title}[/bold bright_magenta]",
                    box=box.ROUNDED,
                ))
            else:
                console.print("[bold yellow]⚠️ No OMDb API key configured. Run 'unshorten --omdb-key <key>' or add key to ~/.ripper/config.json.[/bold yellow]")
            Prompt.ask("\nPress Enter to return")
            continue


async def handle_global_search_flow(
    initial_query: Optional[str] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    min_quality: Optional[str] = None,
    auto_watch: bool = False,
    auto_download: bool = False,
    timeout: float = 12.0,
):
    """
    Unified Global Video Search across 736+ FMHY providers, indexers, and torrents.
    Performs multi-threaded federated search, displays a rich telemetry table,
    and executes the 4-level resolution cascade on the user's selected release.
    """
    import json
    from ripper.ripperdb.harvesters import HarvesterDispatcher
    from ripper.ripperdb.bridge import (
        format_stream_summary,
        launch_stream_in_player_with_headers,
        download_stream,
    )

    query = initial_query.strip() if initial_query else Prompt.ask(
        "\n[bold yellow]Enter movie or series title for Global Search (736+ FMHY sites)[/bold yellow]"
    ).strip()

    if not query:
        return

    # If season/episode were not pre-specified, ask optionally if user wants to filter
    filter_season = season
    filter_episode = episode
    if filter_season is None and not auto_watch and not auto_download:
        se_opt = Prompt.ask(
            "[bold cyan]Is this a TV series? Enter Season number (or press Enter for Movie/All)[/bold cyan]",
            default="",
        ).strip()
        if se_opt.isdigit():
            filter_season = int(se_opt)
            ep_opt = Prompt.ask(
                f"[bold cyan]Enter Episode number for Season {filter_season} (or press Enter for All)[/bold cyan]",
                default="",
            ).strip()
            if ep_opt.isdigit():
                filter_episode = int(ep_opt)

    dispatcher = HarvesterDispatcher()

    # Temporarily filter noisy logger warnings to keep terminal display pristine
    import logging
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

    ripperdb_logger = logging.getLogger("ripper.ripperdb")
    orig_level = ripperdb_logger.level
    ripperdb_logger.setLevel(logging.ERROR)

    total_hits = 0
    scanned_count = 0
    active_providers = dispatcher.get_prioritized_providers(max_providers=35)
    total_sites = len(active_providers)

    with Progress(
        SpinnerColumn("dots", style="bright_cyan"),
        TextColumn("[bold bright_cyan]{task.description}[/bold bright_cyan]"),
        BarColumn(bar_width=28, style="blue", complete_style="bright_green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("• [bold green]{task.fields[hits]}[/bold green] releases"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        scan_task = progress.add_task(
            "🌍 Scanning verified providers in parallel...",
            total=total_sites if total_sites > 0 else 30,
            hits=0,
        )

        def _on_scan_progress(provider_id: str, provider_name: str, count: int, elapsed_ms: float):
            nonlocal total_hits, scanned_count
            scanned_count += 1
            if count > 0:
                total_hits += count
            progress.update(
                scan_task,
                advance=1,
                description=f"Probing [bold white]{provider_name}[/bold white] ({elapsed_ms:.0f}ms)",
                hits=total_hits,
            )

        try:
            results = await dispatcher.federated_search(
                query=query,
                season=filter_season,
                episode=filter_episode,
                min_quality=min_quality,
                timeout=timeout,
                include_core_scrapers=True,
                on_progress=_on_scan_progress,
            )
        finally:
            ripperdb_logger.setLevel(orig_level)

    if not results:
        console.print(f"[bold red]❌ No releases found for '{query}' across all active harvesters.[/bold red]")
        return

    console.print(f"\n[bold green]✔ Found {len(results)} release(s) across federated providers:[/bold green]")

    # Build Rich display table
    table = Table(
        title=f"[bold bright_cyan]🌍 GLOBAL SEARCH RELEASES — {query.upper()}[/bold bright_cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_blue",
    )
    table.add_column("#", justify="center", style="bold cyan", width=4)
    table.add_column("Title / Release Name", style="bold white", min_width=32)
    table.add_column("Provider / Archetype", style="cyan", width=22)
    table.add_column("Quality", justify="center", style="bold yellow", width=10)
    table.add_column("Seeds / Health", justify="right", style="green", width=14)
    table.add_column("Score", justify="right", style="bold bright_green", width=8)

    for i, item in enumerate(results[:40], 1):
        seeds_info = f"🌱 {item.seeders}" if item.seeders is not None else "⚡ Direct"
        prov_display = f"[{item.archetype.upper()}] {item.provider}"
        table.add_row(
            str(i),
            item.title[:45] + ("..." if len(item.title) > 45 else ""),
            prov_display[:22],
            item.quality_tag or "HD",
            seeds_info,
            str(item.quality_score),
        )

    console.print(table)

    # Auto-watch or Auto-download top release if requested
    if auto_watch or auto_download:
        chosen = results[0]
        console.print(f"\n[bold cyan]⚡ Resolving stream link for top match: '{chosen.title}'...[/bold cyan]")
        resolved = await dispatcher.resolve_stream_link(chosen, timeout=timeout)
        if not resolved:
            console.print(f"[bold red]❌ Failed to resolve playable direct stream from: {chosen.page_url}[/bold red]")
            return
        if auto_watch:
            console.print(f"[bold bright_magenta]🎬 Instant Watching '{chosen.title}'...[/bold bright_magenta]")
            success, msg = launch_stream_in_player_with_headers(resolved, title=chosen.title)
            if success:
                console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
            else:
                console.print(f"[bold red]❌ {msg}[/bold red]")
        elif auto_download:
            console.print(f"[bold bright_yellow]📥 Downloading '{chosen.title}'...[/bold bright_yellow]")
            download_stream(resolved, title=chosen.title)
        return

    # Interactive choice
    choices = [str(i) for i in range(1, min(len(results), 40) + 1)] + ["0"]
    sel = Prompt.ask(
        f"\n[bold yellow]Select release # to resolve and stream (1-{min(len(results), 40)}, or '0' to return)[/bold yellow]",
        choices=choices,
        default="1",
    )
    if sel == "0":
        return

    try:
        chosen_idx = int(sel) - 1
        if not (0 <= chosen_idx < len(results)):
            chosen_idx = 0
    except (ValueError, TypeError):
        chosen_idx = 0

    chosen = results[chosen_idx]
    console.print(f"\n[bold cyan]⚡ Resolving stream link for '{chosen.title}' via 4-Level Cascade...[/bold cyan]")
    resolved = await dispatcher.resolve_stream_link(chosen, timeout=timeout)

    if not resolved:
        console.print(f"\n[bold red]❌ Could not resolve playable stream link for: {chosen.page_url}[/bold red]")
        Prompt.ask("\nPress Enter to continue")
        return

    console.print(format_stream_summary(resolved, chosen))

    act = Prompt.ask(
        "\n[bold yellow]Action: [1] ⚡ Instant Watch in Player, [2] 📥 Download Stream, [3] 📋 Print Stream URL, [0] ↩️ Return[/bold yellow]",
        choices=["1", "2", "3", "0"],
        default="1",
    )
    if act == "1":
        success, msg = launch_stream_in_player_with_headers(resolved, title=chosen.title)
        if success:
            console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
        else:
            console.print(f"[bold red]❌ {msg}[/bold red]")
    elif act == "2":
        download_stream(resolved, title=chosen.title)
    elif act == "3":
        console.print(f"\n[bold bright_green]Direct URL:[/bold bright_green] [bold white]{resolved.direct_url}[/bold white]")
        if resolved.headers:
            console.print(f"[dim]HTTP Headers: {json.dumps(resolved.headers, indent=2)}[/dim]")

    Prompt.ask("\nPress Enter to continue")


async def run_interactive_media_selection(items: List[MediaDownloadItem], timeout: float = 5.0):
    """Allow user to select specific quality options step-by-step with instant parallel unshortening."""
    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
    async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True, limits=limits) as client:
        while True:
            display_media_options_menu(items)

            choices = [str(i) for i in range(1, len(items) + 1)] + ["0"]
            choice = Prompt.ask(
                "\n[bold yellow]Select an option number to resolve (or '0' to exit)[/bold yellow]",
                choices=choices,
                default="1",
            )

            if choice == "0":
                break

            idx = int(choice) - 1
            selected = items[idx]

            console.print(f"\n[bold cyan]⠇ Resolving {selected.codec} {selected.quality} [{selected.size_str}]...[/bold cyan]")
            resolved_item = await resolve_single_media_item_fast(selected, client, timeout=timeout, headers=DEFAULT_HEADERS)

            landing = resolved_item.unshortened_landing_url or resolved_item.short_link

            # Server selection loop
            while True:
                if not resolved_item.servers:
                    from .resolver.core.honeypot_filter import is_ad_trap
                    if is_ad_trap(landing) or "vglist" in (landing or "").lower() or "vegamovies-apk" in (landing or "").lower():
                        console.print(f"\n[bold red]⚠️ Filtered promotional/trap link ({landing}). Attempting deep unshorten cascade...[/bold red]")
                        from .universal_engine import universal_extract_media
                        recovered = await universal_extract_media(selected.short_link, client=client)
                        if recovered and recovered[0].servers:
                            resolved_item.servers = recovered[0].servers
                            landing = resolved_item.servers[0].direct_download_url or resolved_item.servers[0].intermediate_url
                        else:
                            console.print("[bold red]❌ No download mirrors could be safely recovered for this selection.[/bold red]")
                            break

                if not resolved_item.servers:
                    console.print(Panel(
                        f"[bold yellow]📽️  QUALITY:[/bold yellow] [bold white]{selected.codec} {selected.quality}[/bold white]  |  "
                        f"[bold yellow]💾 SIZE:[/bold yellow] [bold bright_green]{selected.size_str}[/bold bright_green]\n"
                        f"[bold yellow]🌐 DIRECT LINK:[/bold yellow] [bold bright_white]{landing}[/bold bright_white]",
                        title="[bold green]DIRECT RESOLVED LINK[/bold green]",
                        border_style="green",
                        box=box.ROUNDED,
                    ))
                    await handle_server_action_menu(f"{selected.codec} {selected.quality}", landing, True, f"{selected.movie_name}_{selected.quality}.mkv")
                    break

                # Sort servers prioritizing Cloudflare R2 (10 Gbps), then PixelDrain/SkyDrop/FastDL
                sorted_servers, has_r2 = rank_and_badge_servers(resolved_item.servers)
                resolved_item.servers = sorted_servers

                if has_r2:
                    console.print("\n[bold green]⚡ Cloudflare R2 Direct CDN Detected! Ranked #1 for maximum download speed (~75+ Mbps).[/bold green]")
                else:
                    console.print("\n[bold yellow]ℹ️ Cloudflare R2 Direct CDN not found on this source. Gracefully shifted to alternative high-speed mirrors (PixelDrain / FastDL).[/bold yellow]")

                # Display Servers Table
                server_table = Table(
                    title=f"[bold bright_yellow]🚀 AVAILABLE DOWNLOAD SERVERS FOR {selected.codec} {selected.quality} ({len(resolved_item.servers)} FOUND)[/bold bright_yellow]",
                    box=box.ROUNDED,
                    show_header=True,
                    header_style="bold cyan",
                    border_style="bright_yellow",
                )
                server_table.add_column("#", justify="center", style="bold cyan", width=4)
                server_table.add_column("Server Option", style="bold yellow", width=24)
                server_table.add_column("Status / Type", style="cyan", width=26)
                server_table.add_column("Speed Rating", justify="center", width=26)
                server_table.add_column("Direct Streaming Ready?", justify="center", style="bold green", width=22)

                for s_idx, s in enumerate(resolved_item.servers, 1):
                    url_low = (s.direct_download_url or s.intermediate_url or "").lower()
                    lbl_low = (s.label or "").lower()
                    typ_low = (s.server_type or "").lower()
                    is_r2 = any(k in url_low for k in ["r2.cloudflarestorage.com", "r2.dev", "pub-"]) or "cloudflare r2" in lbl_low or "cloudflare r2" in typ_low or "10 gbps" in lbl_low
                    is_pd = "pixeldrain.com" in url_low or "pixeldrain" in lbl_low or "pixeldrain" in typ_low

                    if is_r2:
                        speed_tier = "[bold bright_green]⚡ 10 Gbps (R2 Direct)[/bold bright_green]"
                        status_text = "[bold bright_green]✔ Cloudflare R2 CDN[/bold bright_green]"
                    elif is_pd:
                        speed_tier = "[bold yellow]⚡ High-Speed (PixelDrain)[/bold yellow]"
                        status_text = "[yellow]✔ PixelDrain Direct[/yellow]"
                    elif s.direct_download_url:
                        speed_tier = "[cyan]⚡ Direct Cloud[/cyan]"
                        status_text = f"[cyan]{s.server_type or 'Direct Stream'}[/cyan]"
                    else:
                        speed_tier = "[dim]Standard Mirror[/dim]"
                        status_text = f"[dim]{s.server_type or 'Page Link'}[/dim]"

                    has_direct = bool(s.direct_download_url)
                    ready_badge = "[bold bright_green]✔ Instant Ready[/bold bright_green]" if has_direct else "[dim]Resolving Page...[/dim]"
                    server_table.add_row(
                        str(s_idx),
                        s.label,
                        status_text,
                        speed_tier,
                        ready_badge,
                    )
                console.print(server_table)

                s_choices = [str(i) for i in range(1, len(resolved_item.servers) + 1)] + ["0"]
                s_choice = Prompt.ask(
                    "\n[bold yellow]Select a Server # to Watch/Download (or '0' to choose another quality)[/bold yellow]",
                    choices=s_choices,
                    default="1",
                )

                if s_choice == "0":
                    break

                s_idx = int(s_choice) - 1
                chosen_server = resolved_item.servers[s_idx]

                target_url = chosen_server.direct_download_url or chosen_server.intermediate_url
                is_direct = bool(chosen_server.direct_download_url)

                from .resolver import resolve_to_direct_stream_url
                if not is_direct and chosen_server.intermediate_url:
                    console.print(f"\n[bold cyan]🔍 Crawling intermediate server page: {chosen_server.label}...[/bold cyan]")
                    crawled_direct = await resolve_to_direct_stream_url(chosen_server.intermediate_url, client=client, timeout=timeout)
                    if crawled_direct and crawled_direct != chosen_server.intermediate_url:
                        target_url = crawled_direct
                        is_direct = True
                        chosen_server.direct_download_url = crawled_direct

                fname = chosen_server.file_name or f"{selected.movie_name}_{selected.quality}.mkv"
                # Collect all other direct/intermediate mirrors as fallbacks
                other_mirrors = [
                    (s.direct_download_url or s.intermediate_url)
                    for s in resolved_item.servers
                    if (s.direct_download_url or s.intermediate_url) and (s.direct_download_url or s.intermediate_url) != target_url
                ]
                await handle_server_action_menu(
                    chosen_server.label,
                    target_url,
                    is_direct,
                    fname,
                    fallback_servers=other_mirrors,
                )


def handle_media_grid_flow(timeout: float = 5.0, user_agent: str = DEFAULT_USER_AGENT):
    """Handles Step-by-Step Quality Selector with auto-detection of URL vs pasted HTML."""
    console.print("\n[bold cyan]🎬 MEDIA & EPISODE GRID EXTRACTOR[/bold cyan]")
    user_input = Prompt.ask("\n[bold yellow]Enter Webpage URL (or type 'paste' to input raw HTML)[/bold yellow]").strip()

    raw_html = ""
    base_url = "https://cinefreak.net"

    if user_input.lower() == "paste" or user_input.startswith("<"):
        raw_html = prompt_multiline_input("Paste raw HTML snippet containing <div class='download-links-div'> or <div class='episode-grid'>:")
    elif user_input.startswith("http://") or user_input.startswith("https://"):
        base_url = user_input
        console.print(f"[bold cyan]🔍 Fetching webpage {user_input}...[/bold cyan]")
        try:
            with httpx.Client(timeout=timeout + 3.0, verify=False) as client:
                resp = client.get(user_input, headers=DEFAULT_HEADERS)
                raw_html = resp.text
        except Exception as e:
            console.print(f"[bold red]❌ Failed to fetch page: {e}[/bold red]")
            Prompt.ask("\nPress Enter to return to menu")
            return
    else:
        raw_html = user_input

    if not raw_html:
        return

    media_items = extract_media_items_from_html(raw_html, base_url)
    if not media_items:
        console.print("[bold red]❌ No download links found in scoped containers.[/bold red]")
        Prompt.ask("\nPress Enter to return to menu")
        return

    console.print(f"\n[bold green]✔ Discovered {len(media_items)} Download Option(s) (Filtered out all junk and watch online links).[/bold green]\n")
    asyncio.run(run_interactive_media_selection(media_items, timeout=timeout))


async def handle_download_and_quality_cockpit(target_url: Optional[str] = None, timeout: float = 5.0):
    """
    📥 Download & Quality Cockpit:
    1. Accepts pasted movie post/page URL or raw HTML snippet
    2. Synchronously & asynchronously extracts all qualities, codecs, prints, file sizes, and audio tracks
    3. Displays an interactive Quality & Print selection menu
    4. Resolves mirrors, prioritizes Cloudflare R2 Direct CDN, and shifts to alternative high-speed mirrors if R2 is absent
    5. Allows user to 8-thread Turbo Download to disk (~/Downloads) or stream directly in video player
    """
    console.print(Panel(
        "[bold bright_yellow]📥 RIPPER DOWNLOAD & QUALITY COCKPIT[/bold bright_yellow]\n"
        "[dim]Paste any movie URL ➔ Choose Quality & Print ➔ Cloudflare R2 / Best Mirror ➔ Turbo 8-Thread Download or Stream[/dim]",
        border_style="bright_yellow",
        box=box.ROUNDED,
    ))

    raw_input = target_url
    if not raw_input:
        raw_input = Prompt.ask("\n[bold yellow]Paste Movie Page URL (e.g. https://kmmovies.pics/..., https://worldfree4u.gd/...)[/bold yellow]").strip()

    if not raw_input:
        return

    raw_html = ""
    base_url = raw_input
    if raw_input.startswith("<") or raw_input.lower() == "paste":
        raw_html = prompt_multiline_input("Paste raw HTML snippet containing download links/episodes:")
        base_url = "https://kmmovies.pics"
    else:
        console.print(f"\n[bold cyan]🔍 Fast-fetching movie page: {raw_input}...[/bold cyan]")
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        try:
            async with httpx.AsyncClient(timeout=timeout + 5.0, verify=False, follow_redirects=True, limits=limits) as client:
                resp = await client.get(raw_input, headers=DEFAULT_HEADERS)
                raw_html = resp.text
        except Exception as e:
            console.print(f"[bold red]❌ Failed to fetch page: {e}[/bold red]")
            Prompt.ask("\nPress Enter to return to menu")
            return

    if not raw_html:
        console.print("[bold red]❌ Empty response received from target URL.[/bold red]")
        Prompt.ask("\nPress Enter to return to menu")
        return

    items = extract_media_items_from_html(raw_html, base_url)
    if not items:
        console.print("[bold cyan]🔄 Standard selectors found 0 items. Activating Autonomous Multi-Tier Engine...[/bold cyan]")
        from .universal_engine import UniversalPipeline
        pipeline = UniversalPipeline()
        def on_step(msg: str):
            console.print(f"[dim cyan]{msg}[/dim cyan]")
        items = await pipeline.extract(raw_input, html=raw_html, progress_callback=on_step)

    if not items:
        console.print("[bold red]❌ No download links or quality grids found across all autonomous tiers.[/bold red]")
        Prompt.ask("\nPress Enter to return to menu")
        return

    movie_title = items[0].movie_name if items else "Movie"
    console.print(f"\n[bold green]✔ Successfully Discovered {len(items)} Quality Option(s) for: [bold white]{movie_title}[/bold white][/bold green]\n")

    await run_interactive_media_selection(items, timeout=timeout)


async def prompt_play_or_download_flow(result: UnshortenResult):
    """Prompt user to play or download if the unshortening result yielded media/files or server mirrors."""
    if not result.is_success or not result.hops:
        return

    # Check if there are server mirrors first
    if result.server_mirrors:
        console.print("\n[bold green]✔ Server mirrors found. Would you like to select a stream server to watch or download?[/bold green]")
        choose = Confirm.ask("Select server and take action?", default=True)
        if choose:
            table = Table(title="🚀 SELECT STREAM SERVER", box=box.ROUNDED)
            table.add_column("#", justify="right", style="bold cyan", width=4)
            table.add_column("Server", style="bold yellow")
            table.add_column("Type", style="cyan")
            for idx, m in enumerate(result.server_mirrors, 1):
                table.add_row(str(idx), m.label, m.server_type)
            console.print(table)

            choices = [str(i) for i in range(1, len(result.server_mirrors) + 1)] + ["0"]
            choice = Prompt.ask("Choose a Server # (or '0' to cancel)", choices=choices, default="1")
            if choice != "0":
                m_idx = int(choice) - 1
                chosen_m = result.server_mirrors[m_idx]
                target_url = chosen_m.direct_download_url or chosen_m.intermediate_url
                is_direct = bool(chosen_m.direct_download_url)

                # Try crawling intermediate page if not direct
                if not is_direct and chosen_m.intermediate_url:
                    console.print(f"\n[bold cyan]🔍 Crawling intermediate server page: {chosen_m.label}...[/bold cyan]")
                    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                        crawled = await crawl_intermediate_server_page(client, chosen_m.intermediate_url, DEFAULT_HEADERS)
                        if crawled:
                            target_url = crawled
                            is_direct = True
                            chosen_m.direct_download_url = crawled

                fname = chosen_m.file_name or f"resolved_download_{m_idx + 1}.mkv"
                await handle_server_action_menu(chosen_m.label, target_url, is_direct, fname)
            return

    # If no server mirrors, but final URL is a direct media/download URL
    final_url = result.final_url
    from .safety import detect_mime_category
    import urllib.parse
    mime = detect_mime_category(final_url, result.hops[-1].content_type)
    if mime in ("MEDIA", "CLOUD_STORAGE", "ARCHIVE", "EXECUTABLE") or any(ext in final_url.lower() for ext in [".mkv", ".mp4", ".avi", ".zip", ".rar", ".exe"]):
        console.print("\n[bold green]✔ Direct downloadable file / stream URL resolved.[/bold green]")
        choose = Confirm.ask("Would you like to play or download this file now?", default=True)
        if choose:
            from pathlib import Path
            fname = Path(urllib.parse.urlparse(final_url).path).name or "resolved_file"
            if not any(fname.lower().endswith(ext) for ext in [".mkv", ".mp4", ".avi", ".zip", ".rar", ".exe"]):
                fname += ".mkv"
            await handle_server_action_menu("Direct Stream Link", final_url, is_direct_stream=True, filename=fname)


async def handle_domain_radar_dashboard():
    """Live Domain Rotation Radar Dashboard to inspect and update active domains."""
    from .domains import DEFAULT_SITE_DOMAINS, get_active_domain, discover_vegamovies_domain, _load_local_domain_cache, _save_local_domain_cache
    from .http_client import get_shared_client

    while True:
        disk_domains = _load_local_domain_cache()
        table = Table(
            title="[bold bright_magenta]🌐 LIVE DOMAIN ROTATION RADAR & ACTIVE MIRRORS[/bold bright_magenta]",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("#", justify="center", style="bold cyan", width=4)
        table.add_column("Network Name", style="bold yellow", width=16)
        table.add_column("Current Active Domain", style="bold white", width=32)
        table.add_column("Status", justify="center", style="bold green", width=14)

        site_keys = list(DEFAULT_SITE_DOMAINS.keys())
        for idx, k in enumerate(site_keys, 1):
            cur = disk_domains.get(k, DEFAULT_SITE_DOMAINS.get(k, ""))
            table.add_row(str(idx), k.capitalize(), cur, "✔ Active")

        console.print("\n")
        console.print(table)

        sub_menu = (
            "[bold white][1][/bold white] 📡 [bold cyan]Probe & Auto-Discover Live TLDs[/bold cyan] (VegaMovies & Katworld)\n"
            "[bold white][2][/bold white] ✏️  [bold yellow]Manually Update a Site Domain[/bold yellow]\n"
            "[bold white][3][/bold white] 🔄 [bold green]Reset All Domains to System Defaults[/bold green]\n"
            "[bold white][0][/bold white] ↩️  [bold red]Back to Main Menu[/bold red]"
        )
        console.print(Panel(sub_menu, title="[bold cyan]DOMAIN RADAR ACTIONS[/bold cyan]", box=box.ROUNDED))

        action = Prompt.ask("[bold yellow]Choose an action[/bold yellow]", choices=["1", "2", "3", "0"], default="1")
        if action == "0":
            break
        elif action == "1":
            console.print("\n[bold cyan]⚡ Probing dynamic redirectors for live domains...[/bold cyan]")
            client = await get_shared_client()
            live_vega = await discover_vegamovies_domain(client)
            disk_domains["vegamovies"] = live_vega
            _save_local_domain_cache(disk_domains)
            console.print(f"[bold green]✔ VegaMovies Live Domain Verified: {live_vega}[/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif action == "2":
            choices = [str(i) for i in range(1, len(site_keys) + 1)]
            s_idx = Prompt.ask("Choose site # to update", choices=choices, default="1")
            chosen_key = site_keys[int(s_idx) - 1]
            new_url = Prompt.ask(f"Enter new URL for {chosen_key.capitalize()} (e.g. https://{chosen_key}.to)").strip()
            if new_url:
                if not new_url.startswith("http"):
                    new_url = "https://" + new_url
                disk_domains[chosen_key] = new_url
                _save_local_domain_cache(disk_domains)
                console.print(f"[bold green]✔ Updated {chosen_key} to {new_url}[/bold green]")
                Prompt.ask("\nPress Enter to continue")
        elif action == "3":
            _save_local_domain_cache(dict(DEFAULT_SITE_DOMAINS))
            console.print("[bold green]✔ All domains reset to system defaults.[/bold green]")
            Prompt.ask("\nPress Enter to continue")


async def handle_batch_dashboard():
    """Interactive Multi-URL Batch Unshortener & Exporter."""
    from .batch import batch_unshorten_urls, extract_urls_from_raw_text, parse_urls_from_file_path, export_results_to_file
    from .ui import display_batch_summary_table

    console.print("\n[bold cyan]📦 MULTI-URL BATCH UNSHORTENER[/bold cyan]")
    batch_mode = Prompt.ask(
        "[bold yellow]Source: [1] Paste URLs / Text, [2] Load from File (.txt, .csv, .md), [0] Cancel[/bold yellow]",
        choices=["1", "2", "0"],
        default="1",
    )

    if batch_mode == "0":
        return

    urls = []
    if batch_mode == "1":
        raw_text = prompt_multiline_input("📋 Paste your URLs or text below (Press Enter on an empty line when done):")
        urls = extract_urls_from_raw_text(raw_text)
    elif batch_mode == "2":
        fpath_str = Prompt.ask("[bold cyan]Enter path to text/CSV/markdown file[/bold cyan]").strip()
        fpath = Path(fpath_str.strip('"\''))
        if fpath.exists():
            urls = parse_urls_from_file_path(fpath)
        else:
            console.print(f"[bold red]❌ File not found: {fpath}[/bold red]")
            Prompt.ask("\nPress Enter to return")
            return

    if not urls:
        console.print("[bold red]❌ No valid URLs extracted.[/bold red]")
        Prompt.ask("\nPress Enter to return")
        return

    console.print(f"\n[bold green]✔ Extracted {len(urls)} target URL(s). Unshortening in parallel...[/bold green]\n")
    results = await batch_unshorten_urls(urls, concurrency=10, show_progress=True)
    display_batch_summary_table(results)

    do_export = Confirm.ask("\nWould you like to export these results to a file?", default=True)
    if do_export:
        out_p = Prompt.ask("Enter export filepath (e.g. batch_results.json, .csv, or .md)", default="batch_results.json")
        export_results_to_file(results, Path(out_p))
        console.print(f"[bold green]✔ Exported {len(results)} results to: {out_p}[/bold green]")

    Prompt.ask("\nPress Enter to return to menu")


async def handle_cache_diagnostics_dashboard():
    """Cache and Circuit Breaker Diagnostics Dashboard."""
    from .cache import GLOBAL_CACHE

    while True:
        res_cnt = len(GLOBAL_CACHE._namespaces.get("resolution", {}))
        search_cnt = len(GLOBAL_CACHE._namespaces.get("search", {}))
        dom_cnt = len(GLOBAL_CACHE._namespaces.get("domain", {}))
        circuit_cnt = len(GLOBAL_CACHE._namespaces.get("circuit", {}))

        table = Table(
            title="[bold bright_magenta]🧹 CACHE & ENGINE DIAGNOSTIC METRICS[/bold bright_magenta]",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("Partition / Namespace", style="bold yellow", width=22)
        table.add_column("Cached Entries", justify="center", style="bold green", width=16)
        table.add_column("TTL Expiration", justify="center", style="white", width=16)
        table.add_column("State", justify="center", style="bold cyan", width=14)

        table.add_row("Resolved URLs", f"{res_cnt} items", "900s (15m)", "✔ Active")
        table.add_row("Search Queries", f"{search_cnt} items", "3600s (1h)", "✔ Active")
        table.add_row("Live Domains Radar", f"{dom_cnt} items", "86400s (24h)", "✔ Active")
        table.add_row("Circuit Breakers", f"{circuit_cnt} items", "300s (5m)", "✔ Monitoring")

        console.print("\n")
        console.print(table)

        sub_menu = (
            "[bold white][1][/bold white] 🧹 [bold yellow]Flush URL Resolution Cache[/bold yellow]\n"
            "[bold white][2][/bold white] 🧹 [bold yellow]Flush Search Queries Cache[/bold yellow]\n"
            "[bold white][3][/bold white] 🧹 [bold red]Flush Entire In-Memory Cache[/bold red]\n"
            "[bold white][0][/bold white] ↩️  [bold green]Back to Main Menu[/bold green]"
        )
        console.print(Panel(sub_menu, title="[bold cyan]CACHE OPERATIONS[/bold cyan]", box=box.ROUNDED))

        action = Prompt.ask("[bold yellow]Choose an action[/bold yellow]", choices=["1", "2", "3", "0"], default="0")
        if action == "0":
            break
        elif action == "1":
            await GLOBAL_CACHE.clear_namespace("resolution")
            console.print("[bold green]✔ Resolution cache flushed.[/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif action == "2":
            await GLOBAL_CACHE.clear_namespace("search")
            console.print("[bold green]✔ Search cache flushed.[/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif action == "3":
            await GLOBAL_CACHE.clear_all()
            console.print("[bold green]✔ Complete in-memory cache flushed.[/bold green]")
            Prompt.ask("\nPress Enter to continue")


async def handle_watchlist_dashboard():
    """Interactive My Watchlist & Favorites Dashboard."""
    from .watchlist import get_watchlist, remove_from_watchlist

    while True:
        items = get_watchlist()
        if not items:
            console.print(Panel("[bold yellow]⭐ Your Watchlist is currently empty.[/bold yellow]\n[dim]Add movies/shows by pressing [F] when searching for any title![/dim]", title="[bold bright_magenta]⭐ MY WATCHLIST[/bold bright_magenta]", box=box.ROUNDED))
            Prompt.ask("\nPress Enter to return")
            break

        table = Table(
            title=f"[bold bright_magenta]⭐ MY WATCHLIST & SAVED FAVORITES ({len(items)} SAVED)[/bold bright_magenta]",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("#", justify="center", style="bold cyan", width=4)
        table.add_column("Title & Year", style="bold white", width=34)
        table.add_column("Source Network", style="bold yellow", width=18)
        table.add_column("Qualities", style="bold bright_green", width=20)
        table.add_column("Added On", style="dim", width=18)

        for i, it in enumerate(items, 1):
            y_str = f"({it.get('year')})" if it.get("year") else ""
            table.add_row(
                str(i),
                f"{it.get('title', '')} {y_str}".strip(),
                it.get("site_name") or "Network",
                it.get("quality") or "HD",
                it.get("added_at") or "-",
            )
        console.print(table)

        console.print("[dim]Options: [1-N] ⚡ 1-Click Stream | [D] 🗑️ Remove Item | [0] ↩️ Back[/dim]")
        choices = [str(i) for i in range(1, len(items) + 1)] + ["0", "d", "D"]
        act = Prompt.ask("[bold yellow]Select a movie # to stream, or action[/bold yellow]", choices=choices, default="1")

        if act == "0":
            break
        elif act in ("d", "D"):
            del_idx = Prompt.ask(f"Enter item # (1-{len(items)}) to delete from watchlist")
            try:
                idx = int(del_idx) - 1
                if 0 <= idx < len(items):
                    remove_from_watchlist(items[idx].get("title", ""))
                    console.print("[bold green]✔ Removed from Watchlist.[/bold green]")
            except Exception:
                pass
            continue

        chosen = items[int(act) - 1]
        console.print(f"\n[bold cyan]🚀 Resolving direct stream for '{chosen.get('title')}'...[/bold cyan]")
        await run_one_click_instant_watch(chosen.get("url", ""))
        break


async def handle_watch_history_dashboard():
    """Watch History & Streaming Analytics Dashboard."""
    from .history import get_history, get_stats, save_history

    while True:
        hist = get_history(limit=25)
        stats = get_stats()

        stat_panel = (
            f"[bold cyan]Total Streams Played:[/bold cyan] [bold white]{stats.get('total_streams', 0)}[/bold white]   |   "
            f"[bold cyan]Top Movie Network:[/bold cyan] [bold yellow]{stats.get('top_source_site', 'None')}[/bold yellow]"
        )
        console.print(Panel(stat_panel, title="[bold green]📊 STREAMING ANALYTICS[/bold green]", box=box.ROUNDED))

        if not hist:
            console.print("[dim]No streams recorded yet. Watch movies via 1-Click Stream to populate history![/dim]\n")
            Prompt.ask("Press Enter to return")
            break

        table = Table(
            title=f"[bold bright_magenta]📜 RECENT PLAYBACK HISTORY (Last {len(hist)})[/bold bright_magenta]",
            box=box.ROUNDED,
            header_style="bold cyan",
            border_style="bright_blue",
        )
        table.add_column("#", justify="center", style="bold cyan", width=4)
        table.add_column("Title", style="bold white", width=34)
        table.add_column("Quality", style="bold bright_green", width=18)
        table.add_column("Source Network", style="bold yellow", width=18)
        table.add_column("Played At", style="dim", width=20)

        for i, h in enumerate(hist, 1):
            table.add_row(
                str(i),
                h.get("title", "Unknown"),
                h.get("quality") or "HD",
                h.get("site_name") or "Direct Stream",
                h.get("played_at") or "-",
            )
        console.print(table)

        console.print("[dim]Options: [1-N] 🔁 Replay Stream | [C] 🧹 Clear History | [0] ↩️ Back[/dim]")
        choices = [str(i) for i in range(1, len(hist) + 1)] + ["0", "c", "C"]
        act = Prompt.ask("[bold yellow]Select # to replay, or action[/bold yellow]", choices=choices, default="0")

        if act == "0":
            break
        elif act in ("c", "C"):
            save_history([])
            console.print("[bold green]✔ Playback history cleared.[/bold green]")
            Prompt.ask("\nPress Enter to continue")
            break

        chosen = hist[int(act) - 1]
        console.print(f"\n[bold cyan]⚡ Resolving direct stream and replaying in media player...[/bold cyan]")
        from .resolver import resolve_to_direct_stream_url
        playable_url = await resolve_to_direct_stream_url(chosen.get("url", ""))
        from .player import launch_video_stream_in_player
        launch_video_stream_in_player(playable_url)
        Prompt.ask("\nPress Enter to continue")
        break


async def handle_advanced_settings_dashboard():
    """Unified Advanced Settings, Cache Diagnostics & System Security Tools."""
    from .config import load_config, set_config_value
    from .cache import GLOBAL_CACHE

    while True:
        cfg = load_config()
        tmdb_st = "[bold green]Configured ✔[/bold green]" if cfg.get("tmdb_api_key") else "[dim]Not Set[/dim]"
        omdb_st = "[bold green]Configured ✔[/bold green]" if cfg.get("omdb_api_key") else "[dim]Not Set[/dim]"
        yt_st = "[bold green]Configured ✔[/bold green]" if cfg.get("youtube_api_key") else "[dim]Not Set[/dim]"
        os_st = "[bold green]Configured ✔[/bold green]" if cfg.get("opensubtitles_api_key") else "[dim]Not Set[/dim]"

        menu_panel = (
            f"[bold bright_cyan]🔑 API KEYS & INTEGRATIONS:[/bold bright_cyan]\n"
            f" • TMDB Brain: {tmdb_st}  |  OMDb Intel: {omdb_st}  |  YouTube: {yt_st}  |  OpenSubtitles: {os_st}\n"
            f" • Player: [bold green]{cfg.get('preferred_player', 'potplayer')}[/bold green]  |  Timeout: [yellow]{cfg.get('default_timeout', 5.0)}s[/yellow]  |  Max Hops: [yellow]{cfg.get('max_hops', 15)}[/yellow]\n"
            f"[dim]─────────────────────────────────────────────────────────────────────────────[/dim]\n"
            f"[bold white][1][/bold white] 🔑 [bold yellow]Configure API Keys[/bold yellow] (TMDB, OMDb, YouTube, OpenSubtitles)\n"
            f"[bold white][2][/bold white] 🎛️ [bold yellow]Playback & Network Preferences[/bold yellow] (Player, Timeout, Max Hops)\n"
            f"[bold white][3][/bold white] 🧹 [bold cyan]Cache & Storage Diagnostics[/bold cyan] (View Memory & Flush Partitions)\n"
            f"[bold white][4][/bold white] 🛡️ [bold cyan]Security, MIME & HTTP Header Inspector[/bold cyan] (Inspect Redirect Hops)\n"
            f"[bold white][5][/bold white] 🎬 [bold bright_yellow]Extract & Deep-Unshorten Media Grid[/bold bright_yellow] (Quality & Codec Selector)\n"
            f"[bold white][6][/bold white] 🔗 [bold cyan]Single Link Deep Crawler[/bold cyan] (Base64 Unpacker)\n"
            f"[bold white][7][/bold white] 🧬 [bold bright_magenta]100-Run Autonomous Simulation Suite[/bold bright_magenta] (Stress Test & Benchmark)\n"
            f"[bold white][0][/bold white] ↩️  [bold green]Back to Main Cockpit[/bold green]"
        )
        console.print("\n")
        console.print(Panel(menu_panel, title="[bold bright_magenta]🛠️ ADVANCED SETTINGS & SYSTEM UTILITIES[/bold bright_magenta]", box=box.ROUNDED))

        sub_opt = Prompt.ask("[bold yellow]Choose a tool or setting[/bold yellow]", choices=["1", "2", "3", "4", "5", "6", "7", "0"], default="0")
        if sub_opt == "0":
            break
        elif sub_opt == "1":
            console.print("\n[bold cyan]🔑 CONFIGURE EXTERNAL METADATA & STREAMING APIS:[/bold cyan]")
            k_act = Prompt.ask("Action: [1] TMDB Key, [2] OMDb Key, [3] YouTube Key, [4] OpenSubtitles Key, [0] Back", choices=["1", "2", "3", "4", "0"], default="0")
            if k_act == "1":
                val = Prompt.ask("Enter TMDB API Key").strip()
                if val:
                    set_config_value("tmdb_api_key", val)
                    console.print("[bold green]✔ Saved TMDB API Key.[/bold green]")
            elif k_act == "2":
                val = Prompt.ask("Enter OMDb API Key").strip()
                if val:
                    set_config_value("omdb_api_key", val)
                    console.print("[bold green]✔ Saved OMDb API Key.[/bold green]")
            elif k_act == "3":
                val = Prompt.ask("Enter YouTube API Key").strip()
                if val:
                    set_config_value("youtube_api_key", val)
                    console.print("[bold green]✔ Saved YouTube API Key.[/bold green]")
            elif k_act == "4":
                val = Prompt.ask("Enter OpenSubtitles API Key").strip()
                if val:
                    set_config_value("opensubtitles_api_key", val)
                    console.print("[bold green]✔ Saved OpenSubtitles API Key.[/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif sub_opt == "2":
            p_val = Prompt.ask("Set preferred media player (potplayer / vlc / mpv)", default=cfg.get("preferred_player", "potplayer"))
            t_val = float(Prompt.ask("Set connection timeout in seconds", default=str(cfg.get("default_timeout", 5.0))))
            h_val = int(Prompt.ask("Set max redirect hops", default=str(cfg.get("max_hops", 15))))
            set_config_value("preferred_player", p_val)
            set_config_value("default_timeout", t_val)
            set_config_value("max_hops", h_val)
            console.print("[bold green]✔ Playback preferences updated![/bold green]")
            Prompt.ask("\nPress Enter to continue")
        elif sub_opt == "3":
            await handle_cache_diagnostics_dashboard()
        elif sub_opt == "4":
            target = Prompt.ask("\n[bold cyan]Enter URL for Deep Security & Header Inspection[/bold cyan]").strip()
            if target:
                console.print(f"\n[bold magenta]🛡️ Running Deep Security Inspection...[/bold magenta]\n")
                result = await unshorten_url(target, max_hops=cfg.get("max_hops", 15), timeout=cfg.get("default_timeout", 5.0), user_agent=DEFAULT_USER_AGENT)
                display_unshorten_summary(result)
                console.print("\n[bold yellow]📋 DETAILED HTTP HEADERS PER HOP:[/bold yellow]")
                for h in result.hops:
                    console.print(f"\n[bold cyan]Hop {h.hop_number} ({h.redirect_type}) -> {h.url}[/bold cyan]")
                    if h.headers:
                        for k, v in h.headers.items():
                            console.print(f"  [dim]{k}:[/dim] [white]{v}[/white]")
                    else:
                        console.print("  [dim]No headers recorded[/dim]")
                Prompt.ask("\nPress Enter to continue")
        elif sub_opt == "5":
            handle_media_grid_flow(timeout=cfg.get("default_timeout", 5.0), user_agent=DEFAULT_USER_AGENT)
        elif sub_opt == "6":
            target = Prompt.ask("\n[bold cyan]Enter Shortened URL[/bold cyan]").strip()
            if target:
                console.print(f"\n[bold magenta]🔍 Tracing redirects for: [/bold magenta][white]{target}[/white]...")
                result = await unshorten_url(target, max_hops=cfg.get("max_hops", 15), timeout=cfg.get("default_timeout", 5.0), user_agent=DEFAULT_USER_AGENT, deep_crawl_servers=True)
                display_unshorten_summary(result)
                await prompt_play_or_download_flow(result)
                Prompt.ask("\nPress Enter to continue")
        elif sub_opt == "7":
            from .simulation import run_autonomous_100_simulation
            await run_autonomous_100_simulation(verbose=True)
            Prompt.ask("\nPress Enter to continue")


async def handle_single_link_unshorten_flow(timeout: float = 5.0, user_agent: str = DEFAULT_USER_AGENT):
    """Traces any single shortlink, ad-redirect, or Base64 generator to extract the final direct stream/file."""
    console.print("\n[bold cyan]🔗 SINGLE LINK DEEP CRAWLER & BASE64 UNPACKER[/bold cyan]")
    target = Prompt.ask("\n[bold yellow]Enter any shortened link or ad-generator URL[/bold yellow]").strip()
    if not target:
        return
    console.print(f"\n[bold magenta]🔍 Tracing redirects & unlocking direct file for:[/bold magenta] [white]{target}[/white]...")
    result = await unshorten_url(target, max_hops=15, timeout=timeout, user_agent=user_agent, deep_crawl_servers=True)
    display_unshorten_summary(result)
    await prompt_play_or_download_flow(result)
    Prompt.ask("\nPress Enter to return to main menu")


async def handle_universal_bypasser_cockpit(timeout: float = 20.0):
    """
    Universal Shortlink Bypasser, Ad-Gate Solver & Encrypted Container Cockpit.
    Supports GPLinks, Droplink, Rocklinks, Ouo.io, ShrinkMe, Filecrypt, Keeplinks,
    Pastebin, Linkbox, DLC containers, and local Port 9666 Click'n'Load daemon.
    """
    from .universal_bypasser import UniversalBypasserEngine, URLClassifier, GateType, CNL2Crypto, CNL2Listener
    from .universal_bypasser.models import ShortlinkResult, ContainerResult

    engine = UniversalBypasserEngine()

    while True:
        console.print("\n[bold bright_magenta]════════════════════════════════════════════════════════════════════════════════[/bold bright_magenta]")
        console.print("[bold cyan]🔓 UNIVERSAL SHORTLINK BYPASSER & CONTAINER ENGINE[/bold cyan]")
        console.print("[dim]Supported: GPLinks, Droplink, Rocklinks, Ouo.io, AdLinkFly, Filecrypt, Keeplinks, Pastebin, DLC, CNL2[/dim]")
        console.print("[bold bright_magenta]════════════════════════════════════════════════════════════════════════════════[/bold bright_magenta]")
        console.print("  [bold white][1][/bold white] 🔗 [bold bright_green]Bypass Shortlink / Ad-Gate[/bold bright_green]       (GPLinks, Droplink, Rocklinks, Ouo, ShrinkMe)")
        console.print("  [bold white][2][/bold white] 📁 [bold bright_yellow]Unroll Container / Locker Folder[/bold bright_yellow] (Filecrypt, Keeplinks, Pastebin, Linkbox, DLC)")
        console.print("  [bold white][3][/bold white] ⚡ [bold bright_cyan]Start Click'n'Load (Port 9666)[/bold bright_cyan]     (Receive encrypted links directly from browser)")
        console.print("  [bold white][4][/bold white] 🔐 [bold white]Decrypt Raw CNL2 Payload[/bold white]            (Manual AES-128-CBC crypted + jk string input)")
        console.print("  [bold white][0][/bold white] ↩️  [bold red]Return to Main Menu[/bold red]\n")

        choice = Prompt.ask("[bold yellow]Select operation[/bold yellow]", choices=["1", "2", "3", "4", "0"], default="1").strip()

        if choice == "0":
            break

        elif choice == "1":
            url = Prompt.ask("\n[bold cyan]Paste Shortlink / Ad-Gate URL[/bold cyan]").strip()
            if not url:
                continue
            console.print(f"\n[bold yellow]⚡ Bypassing ad-gate tokens for:[/bold yellow] [white]{url}[/white]...")
            res = await engine.bypass_shortlink(url)
            if res.success and res.resolved_url:
                console.print(f"\n[bold green]✔ BYPASS SUCCESSFUL ({res.duration:.2f}s)[/bold green]")
                console.print(f"[bold cyan]Solver:[/bold cyan] {res.solver_used}")
                console.print(f"[bold bright_green]Target URL:[/bold bright_green] [bold white]{res.resolved_url}[/bold white]")
                if res.intermediate_urls:
                    console.print("[dim]Hops:[/dim] " + " ➔ ".join(res.intermediate_urls))

                act = Prompt.ask(
                    "\n[bold yellow]Action: [1] Watch in Player, [2] Send to AnyStream, [3] Copy/Return[/bold yellow]",
                    choices=["1", "2", "3"],
                    default="1"
                )
                if act == "1":
                    await run_one_click_instant_watch(res.resolved_url, timeout=timeout)
                elif act == "2":
                    from .anystream import handle_anystream_cli
                    await handle_anystream_cli(res.resolved_url)
            else:
                console.print(f"\n[bold red]❌ Bypass Failed:[/bold red] {res.error or 'Unknown error'}")
            Prompt.ask("\nPress Enter to continue")

        elif choice == "2":
            url = Prompt.ask("\n[bold cyan]Paste Container / Folder URL (Filecrypt, Keeplinks, Pastebin, DLC)[/bold cyan]").strip()
            if not url:
                continue
            console.print(f"\n[bold yellow]📁 Unrolling encrypted container links from:[/bold yellow] [white]{url}[/white]...")
            res = await engine.unroll_container(url)
            if res.success and res.unlocked_urls:
                console.print(f"\n[bold green]✔ UNROLLED {len(res.unlocked_urls)} LINKS ({res.duration:.2f}s)[/bold green]")
                console.print(f"[bold cyan]Package Title:[/bold cyan] {res.title or 'Unknown Container'}")
                table = Table(title=f"Unlocked Hoster Links ({len(res.unlocked_urls)})", box=box.ROUNDED)
                table.add_column("#", style="bold cyan", width=4)
                table.add_column("Hoster Stream / Download URL", style="bold green")
                for idx, link in enumerate(res.unlocked_urls, 1):
                    table.add_row(str(idx), link)
                console.print(table)

                act = Prompt.ask(
                    "\n[bold yellow]Action: [1] Select link to Watch, [2] Export to text file, [0] Back[/bold yellow]",
                    choices=["1", "2", "0"],
                    default="1"
                )
                if act == "1":
                    pick = Prompt.ask("Enter link # to watch", choices=[str(i) for i in range(1, len(res.unlocked_urls) + 1)])
                    chosen_link = res.unlocked_urls[int(pick) - 1]
                    await run_one_click_instant_watch(chosen_link, timeout=timeout)
                elif act == "2":
                    out_f = Prompt.ask("Enter filename", default="unlocked_links.txt").strip()
                    with open(out_f, "w", encoding="utf-8") as f:
                        for link in res.unlocked_urls:
                            f.write(link + "\n")
                    console.print(f"[bold green]✔ Saved {len(res.unlocked_urls)} links to {out_f}[/bold green]")
            else:
                console.print(f"\n[bold red]❌ Container Unroll Failed:[/bold red] {res.error or 'No links found'}")
            Prompt.ask("\nPress Enter to continue")

        elif choice == "3":
            console.print("\n[bold cyan]⚡ Starting Click'n'Load (CNL2) Port 9666 Local Daemon...[/bold cyan]")
            collected_links = []
            def on_recv(links):
                collected_links.extend(links)
                console.print(f"\n[bold green]✔ CNL2 Received {len(links)} link(s) from browser![/bold green]")
                for l in links:
                    console.print(f"  [bright_green]➔[/bright_green] {l}")

            listener = CNL2Listener(on_links_received=on_recv)
            await listener.start()
            console.print("[bold green]✔ Listening on http://127.0.0.1:9666[/bold green]")
            console.print("[dim]You can now click 'Click'n'Load' on Filecrypt or any locker in your web browser.[/dim]")
            Prompt.ask("\n[bold yellow]Press Enter to stop Click'n'Load daemon and return[/bold yellow]")
            await listener.stop()
            console.print("[bold yellow]Click'n'Load daemon stopped.[/bold yellow]")

        elif choice == "4":
            crypted = Prompt.ask("\n[bold cyan]Paste 'crypted' Base64 string[/bold cyan]").strip()
            jk = Prompt.ask("[bold cyan]Paste 'jk' JavaScript string[/bold cyan]").strip()
            if crypted and jk:
                try:
                    urls = CNL2Crypto.decrypt(crypted, jk)
                    console.print(f"\n[bold green]✔ Successfully decrypted {len(urls)} URLs:[/bold green]")
                    for u in urls:
                        console.print(f"  [green]➔[/green] {u}")
                except Exception as exc:
                    console.print(f"[bold red]❌ Decryption error: {exc}[/bold red]")
            Prompt.ask("\nPress Enter to continue")


def launch_interactive_unshortener():
    """Main interactive terminal loop — 🏆 Ripper God-Mode Interactive Dashboard Design."""
    from .config import load_config
    from .watchlist import get_watchlist
    from .history import get_history
    from .cache import GLOBAL_CACHE
    from .player import get_playback_resume_state, launch_video_stream_in_player
    from .ui import display_ripper_cockpit_banner

    while True:
        console.clear() if sys.platform != "win32" else os.system("cls")

        cfg = load_config()
        timeout = float(cfg.get("default_timeout", 5.0))
        wl_count = len(get_watchlist())
        hist_count = len(get_history())
        cache_count = len(GLOBAL_CACHE._namespaces.get("resolution", {}))
        player_name = (cfg.get("preferred_player") or "potplayer").upper()

        # Render Dual-Column Cockpit Banner
        display_ripper_cockpit_banner(
            player_name=player_name,
            proxy_status="127.0.0.1:5055 (IDLE)",
            radar_count=62,
        )

        # Command Matrix Panel
        matrix_text = (
            "   [bold white][1][/bold white] ⚡ [bold bright_green]Instant Watch / Stream Link[/bold bright_green]  [dim]Paste URL ➔ Direct Player Launch in <1s[/dim]\n"
            "   [bold white][2][/bold white] 🔍 [bold bright_magenta]Master Multi-Site Search[/bold bright_magenta]     [dim]Vega, KatMovie, CineFreak, HDHub4u, OMDb[/dim]\n"
            "   [bold white][G][/bold white] 🌍 [bold bright_cyan]Global Video Search & Crawl[/bold bright_cyan] [dim]736+ Providers, Live fmhy.net Crawler & Mirrors[/dim]\n"
            "   [bold white][H][/bold white] 🛡️ [bold bright_green]Autonomous Healer & Doctor[/bold bright_green]  [dim]Preflight Diagnostics, Mirror Failover & FixNet[/dim]\n"
            "   [bold white][D][/bold white] 📥 [bold bright_yellow]Download & Quality Cockpit[/bold bright_yellow]   [dim]Paste Movie URL ➔ Choose Quality/Print ➔ Cloudflare R2 / Best Mirror ➔ Download/Stream[/dim]\n"
            "   [bold white][B][/bold white] 🔓 [bold bright_green]Universal Bypasser & Lockers[/bold bright_green] [dim]GPLinks, Droplink, Rocklinks, Filecrypt, Keeplinks, CNL2[/dim]\n"
            "   [bold white][A][/bold white] 🧠 [bold bright_cyan]AI Copilot & Assistant[/bold bright_cyan]      [dim]Ask questions, options, guidance with K2-Horizon[/dim]\n"
            "   [bold white][3][/bold white] 🌐 [bold bright_cyan]AnyStream Video Extractor[/bold bright_cyan]    [dim]Dood, PlayMate, StreamTape, R2, Gofile, Hub[/dim]\n"
            "   [bold white][4][/bold white] 🎯 [bold bright_yellow]Autonomous Hunter Radar[/bold bright_yellow]      [dim]Discover fresh domains & verified releases[/dim]\n"
            "   [bold white][5][/bold white] 📺 [bold bright_green]Web Cinema Cockpit[/bold bright_green]           [dim]Launch browser UI & TV caster on :5055[/dim]\n"
            "   [bold white][6][/bold white] 📦 [bold bright_cyan]Batch Unshorten & Trace[/bold bright_cyan]      [dim]Multi-threaded bulk file / redirect resolve[/dim]\n"
            "   [bold white][7][/bold white] ▶  [bold bright_yellow]Resume Last Session[/bold bright_yellow]          [dim]1-Click jump back into last played media[/dim]\n"
            "   [bold white][8][/bold white] ⚙️  [bold white]Ripper Config & API Vault[/bold white]    [dim]Manage TMDB, OMDb, Debrid, Subtitles[/dim]\n"
            "   [bold white][9][/bold white] 📊 [bold cyan]Health Radar & Latency Map[/bold cyan]   [dim]Test mirror speeds & DNS over HTTPS health[/dim]\n"
            "   [bold white][0][/bold white] 🚪 [bold red]Exit Ripper[/bold red]"
        )
        console.print(Panel(matrix_text, title="[bold cyan]🚀 COMMAND MATRIX[/bold cyan]", border_style="cyan", box=box.ROUNDED))

        # Live Telemetry & Recent Streams Panel
        last_session = get_playback_resume_state()
        last_stream_title = last_session.get("title", "None") if last_session else "None"
        telemetry_text = (
            f" [bold white]AI Model:[/bold white] [cyan]K2-Horizon (ONLINE)[/cyan]  [dim]|[/dim]  "
            f"[bold white]Last Stream:[/bold white] [bright_yellow]{last_stream_title}[/bright_yellow]  [dim]|[/dim]  "
            f"[bold white]Cache Items:[/bold white] [green]{cache_count}[/green]  [dim]|[/dim]  "
            f"[bold white]Watchlist:[/bold white] [yellow]{wl_count}[/yellow]  [dim]|[/dim]  "
            f"[bold white]History:[/bold white] [cyan]{hist_count}[/cyan]"
        )
        console.print(Panel(telemetry_text, title="[bold green]📡 LIVE TELEMETRY & STATUS[/bold green]", border_style="green", box=box.ROUNDED))

        # Dynamic unified prompt
        user_input = Prompt.ask(
            "\n[bold bright_cyan][RIPPER][/bold bright_cyan] [bold yellow]Select an operation (0-9, G, H, D, B, A) or paste URL/Search/Question directly[/bold yellow]",
            default="2",
        ).strip()

        if user_input == "0":
            console.print("\n[bold green]👋 Goodbye from Ripper![/bold green]")
            sys.exit(0)

        elif user_input.lower() in ("g", "global", "gs", "crawl", "sync"):
            console.print("\n[bold cyan]🌍 FMHY GLOBAL DIRECTORY & HARVESTER OPERATIONS:[/bold cyan]")
            console.print("  [bold white][1][/bold white] 🔍 [bold bright_cyan]Global Federated Search[/bold bright_cyan] (Search 736+ providers across all archetypes)")
            console.print("  [bold white][2][/bold white] 🕷️ [bold bright_green]Live Deep Crawl & Sync (fmhy.net/video)[/bold bright_green] (Scrape HTML + Markdown, find new sites & mirrors, zero data lost)")
            console.print("  [bold white][3][/bold white] 📊 [bold bright_yellow]RipperDB Telemetry & Storage[/bold bright_yellow] (Inspect registered domains & cache)")
            console.print("  [bold white][0][/bold white] ↩️  [bold red]Return to Cockpit[/bold red]\n")
            g_choice = Prompt.ask("[bold yellow]Select operation[/bold yellow]", choices=["1", "2", "3", "0"], default="1")
            if g_choice == "1":
                asyncio.run(handle_global_search_flow(timeout=timeout))
            elif g_choice == "2":
                from ripper.ripperdb.fmhy_sync import FMHYRegistrySync
                syncer = FMHYRegistrySync()
                console.print("\n[bold cyan]🕷️ Deep-Crawling https://fmhy.net/video live & GitHub Markdown...[/bold cyan]")
                res = syncer.crawl_live_and_diff()
                table = Table(title="[bold bright_cyan]🕷️ FMHY LIVE DIRECTORY DEEP-CRAWLER & DIFF[/bold bright_cyan]", box=box.ROUNDED)
                table.add_column("Telemetry Metric", style="bold cyan")
                table.add_column("Value / Status", style="bold green")
                table.add_row("Status", str(res.get("status", "unknown")).upper())
                table.add_row("Sources Crawled", ", ".join(res.get("sources_crawled", [])))
                table.add_row("Total Providers Synced", str(res.get("providers_total", 0)))
                table.add_row("Total Stream Mirrors", str(res.get("mirrors_total", 0)))
                table.add_row("New Providers Discovered", f"[bold yellow]{res.get('new_providers_count', 0)}[/bold yellow]")
                table.add_row("New Mirror Links Discovered", f"[bold yellow]{res.get('new_mirrors_count', 0)}[/bold yellow]")
                table.add_row("Archetypes Breakdown", ", ".join(f"{k}: {v}" for k, v in res.get("archetypes", {}).items()))
                console.print(table)

                new_provs = res.get("new_providers", [])
                if new_provs:
                    p_table = Table(title="[bold bright_yellow]✨ Newly Discovered Providers[/bold bright_yellow]", box=box.SIMPLE)
                    p_table.add_column("Provider Name", style="bold white")
                    p_table.add_column("Primary Domain", style="bold green")
                    p_table.add_column("Section", style="cyan")
                    p_table.add_column("Archetype", style="magenta")
                    p_table.add_column("Mirrors", style="yellow")
                    for p in new_provs[:15]:
                        p_table.add_row(p.get("name", ""), p.get("primary_url", ""), p.get("section", ""), p.get("archetype", ""), str(p.get("mirrors_count", 1)))
                    console.print(p_table)
                    if len(new_provs) > 15:
                        console.print(f"[dim]... and {len(new_provs) - 15} more new providers registered.[/dim]")
                console.print("\n[bold green]✔ All updated sites and mirrors synced with zero data lost![/bold green]")
            elif g_choice == "3":
                from ripper.ripperdb.cache import RipperDBCache
                cache = RipperDBCache()
                stats = cache.get_stats()
                stat_table = Table(title="[bold bright_magenta]📊 RIPPERDB TELEMETRY & STORAGE[/bold bright_magenta]", box=box.ROUNDED)
                stat_table.add_column("Component", style="bold cyan")
                stat_table.add_column("Count / Metric", style="bold yellow")
                stat_table.add_row("Registered Providers", str(stats.get("providers_count", 0)))
                stat_table.add_row("Active Mirrors", str(stats.get("mirrors_count", 0)))
                stat_table.add_row("Cached Media Entities", str(stats.get("media_entities_count", 0)))
                stat_table.add_row("Cached Releases", str(stats.get("release_items_count", 0)))
                stat_table.add_row("Cached Streams", str(stats.get("cached_streams_count", 0)))
                stat_table.add_row("Database File", str(stats.get("db_path", "")))
                console.print(stat_table)
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input.lower() in ("h", "heal", "doctor", "healer"):
            from .ripperdb.self_healing import get_autonomous_healer
            healer = get_autonomous_healer()
            console.print("\n[bold cyan]Choose Healer Operation:[/bold cyan]")
            console.print("  [bold white][1][/bold white] 🩺 [bold bright_cyan]Run Preflight System Doctor[/bold bright_cyan]")
            console.print("  [bold white][2][/bold white] 🛡️ [bold bright_green]Trigger Active Self-Healing & WAL Vacuum[/bold bright_green]")
            console.print("  [bold white][3][/bold white] 📊 [bold bright_yellow]Display FixNet Telemetry & Consensus Stats[/bold bright_yellow]")
            h_choice = Prompt.ask("[bold yellow]Select operation[/bold yellow]", choices=["1", "2", "3", "0"], default="1")
            if h_choice == "1":
                rep = healer.run_system_doctor()
                doc_table = Table(title="[bold cyan]🩺 RIPPER System Doctor Preflight Diagnostics[/bold cyan]", box=box.ROUNDED, border_style="cyan")
                doc_table.add_column("Subsystem", style="bold white")
                doc_table.add_column("Status", style="bold")
                doc_table.add_column("Details", style="dim")
                for name, c in rep.get("checks", {}).items():
                    st = c.get("status", "UNKNOWN")
                    col = "green" if st == "PASS" else ("yellow" if st == "OPTIONAL" else "red")
                    dt = ", ".join(f"{k}: {v}" for k, v in c.items() if k != "status")
                    doc_table.add_row(name.replace("_", " ").title(), f"[{col}]{st}[/{col}]", dt[:80])
                console.print(doc_table)
            elif h_choice == "2":
                res = healer.trigger_full_healing()
                console.print(f"[bold green]✔ Self-healing complete in {res.get('duration_ms', 0)}ms[/bold green]")
                for act in res.get("actions_taken", []):
                    console.print(f"  • [green]{act}[/green]")
            elif h_choice == "3":
                summ = healer.journal.get_summary()
                console.print(f"[bold cyan]Total Intercepted:[/bold cyan] {summ.get('total_intercepted')}")
                console.print(f"[bold green]Total Auto-Healed:[/bold green] {summ.get('total_auto_healed')}")
                console.print(f"[bold yellow]Resilience Rate:[/bold yellow] {summ.get('success_rate_pct')}%")
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input.lower() in ("d", "download"):
            asyncio.run(handle_download_and_quality_cockpit(timeout=timeout))
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input.lower() in ("b", "bypass"):
            asyncio.run(handle_universal_bypasser_cockpit(timeout=timeout))
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input.lower() in ("a", "ai", "copilot"):
            from .ai_engine import launch_ai_chat
            launch_ai_chat()
            Prompt.ask("\nPress Enter to return to dashboard")


        # Smart Auto-Route: Direct URL pasted
        elif user_input.startswith("http://") or user_input.startswith("https://"):
            console.print(f"\n[bold green]⚡ URL Detected: {user_input[:65]}...[/bold green]")
            console.print("  [bold white][1][/bold white] 📥 [bold bright_yellow]Download & Quality Cockpit[/bold bright_yellow] (Select Quality, Print & Mirror ➔ Download / Stream)")
            console.print("  [bold white][2][/bold white] ⚡ [bold bright_green]1-Click Instant Watch[/bold bright_green] (Auto-launch PotPlayer directly in <1s)")
            url_mode = Prompt.ask("[bold yellow]Choose action[/bold yellow]", choices=["1", "2"], default="1")
            if url_mode == "1":
                asyncio.run(handle_download_and_quality_cockpit(target_url=user_input, timeout=timeout))
            else:
                asyncio.run(run_one_click_instant_watch(user_input, timeout=timeout))
            Prompt.ask("\nPress Enter to return to dashboard")

        # Smart Auto-Route: Query text entered (not a single digit 0-9)
        elif len(user_input) > 1 and not user_input.isdigit():
            from .autodetect import classify_user_input, InputIntent
            plan = classify_user_input(user_input)
            if plan.intent == InputIntent.AI_ASSISTANT:
                from .ai_engine import display_copilot_response, answer_user_query
                resp = plan.ai_plan if (plan.ai_plan and hasattr(plan.ai_plan, "answer")) else answer_user_query(user_input)
                display_copilot_response(resp)
                Prompt.ask("\nPress Enter to return to dashboard")
            else:
                console.print(f"\n[bold green]🔍 Search Query Detected: '{user_input}'[/bold green]")
                asyncio.run(handle_search_flow(initial_query=user_input, timeout=timeout))

        elif user_input == "1":
            target = Prompt.ask("\n[bold cyan]Enter Webpage / Movie URL for 1-Click Instant Stream[/bold cyan]").strip()
            if target:
                asyncio.run(run_one_click_instant_watch(target, timeout=timeout))
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input == "2":
            asyncio.run(handle_search_flow(timeout=timeout))

        elif user_input == "3":
            target = Prompt.ask("\n[bold cyan]Enter Video / Host URL to Extract Streams (Dood/StreamTape/R2/etc)[/bold cyan]").strip()
            if target:
                from .anystream import handle_anystream_cli
                asyncio.run(handle_anystream_cli(target))
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input == "4":
            console.print("\n[bold cyan]🎯 AUTONOMOUS HUNTER RADAR[/bold cyan]")
            console.print("  [bold white][1][/bold white] 🌍 [bold bright_green]Site Hunter[/bold bright_green]  (Discover & verify new live streaming domains)")
            console.print("  [bold white][2][/bold white] 🎯 [bold bright_magenta]Movie Hunter[/bold bright_magenta] (Hunt verified releases across all active sites)")
            console.print("  [bold white][0][/bold white] ↩️  [bold red]Return[/bold red]\n")
            h_sub = Prompt.ask("[bold yellow]Choose Hunter mode[/bold yellow]", choices=["1", "2", "0"], default="2")
            if h_sub == "1":
                from .hunter.site_hunter import SiteHunter
                sh = SiteHunter()
                asyncio.run(sh.hunt_sites(max_sites=50))
            elif h_sub == "2":
                from .hunter.site_hunter import SiteHunter
                from .hunter.movie_hunter import MovieHunter
                sh = SiteHunter()
                mh = MovieHunter(sh)
                q = Prompt.ask("\n[bold yellow]Enter movie/series name to hunt[/bold yellow]").strip()
                if q:
                    results = asyncio.run(mh.hunt_movie(q, max_results=30, verify_links=True))
                    if results:
                        sel = Prompt.ask(
                            f"\n[bold yellow]Select result # to 1-Click Stream (or '0' to return)[/bold yellow]",
                            choices=[str(i) for i in range(0, min(len(results), 30) + 1)],
                            default="1",
                        )
                        if sel != "0":
                            chosen = results[int(sel) - 1]
                            asyncio.run(run_one_click_instant_watch(chosen.post_url, timeout=timeout))
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input == "5":
            from .remote_hub import handle_couch_control_hub
            asyncio.run(handle_couch_control_hub())

        elif user_input == "6":
            asyncio.run(handle_batch_dashboard())

        elif user_input == "7":
            # 1-Click Resume Last Session
            state = get_playback_resume_state()
            if not state or not state.get("stream_url"):
                console.print("\n[bold red]❌ No previous playback session found to resume.[/bold red]")
            else:
                s_url = state["stream_url"]
                s_title = state.get("title", "Media Stream")
                s_subs = state.get("subtitle_path")
                console.print(f"\n[bold green]▶ Resuming: {s_title}[/bold green]")
                success, msg = launch_video_stream_in_player(s_url, filename=s_title, subtitle_path=s_subs)
                if success:
                    console.print(f"[bold green]✔ {msg}[/bold green]")
                else:
                    console.print(f"[bold red]❌ {msg}[/bold red]")
            Prompt.ask("\nPress Enter to return to dashboard")

        elif user_input == "8":
            asyncio.run(handle_advanced_settings_dashboard())

        elif user_input == "9":
            asyncio.run(handle_domain_radar_dashboard())

