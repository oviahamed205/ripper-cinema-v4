"""
ripper.ripperdb.bridge
~~~~~~~~~~~~~~~~~~~~~~

Integration bridge connecting ripperdb search and resolved streams directly with:
- Media player launcher (PotPlayer, VLC, MPV) with HTTP headers & subtitles.
- 8-Thread resumable chunk downloader and torrent magnet clients.
- Rich terminal summary formatters for Cockpit display.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from rich import box
from rich.panel import Panel
from rich.table import Table

from ripper.downloader import download_file_fast, sanitize_filename
from ripper.player import (
    detect_available_players,
    launch_video_stream_in_player,
    save_playback_resume_state,
)
from ripper.ripperdb.cache import CachedStream, ReleaseItem
from ripper.ui import console

logger = logging.getLogger("ripper.ripperdb.bridge")


def launch_stream_in_player_with_headers(
    cached_stream: CachedStream,
    title: str = "Media Stream",
) -> Tuple[bool, str]:
    """
    Launches a cached stream in the best available player (PotPlayer, VLC, MPV)
    while forwarding required HTTP headers (Referer, User-Agent) and downloading subtitles.
    """
    direct_url = cached_stream.direct_url
    if not direct_url:
        return False, "Stream URL is empty"

    # 1. Magnet link handling
    if direct_url.startswith("magnet:?"):
        save_playback_resume_state(direct_url, title=title)
        if sys.platform == "win32":
            try:
                os.startfile(direct_url)
                return True, "🧲 Opened magnet link in default BitTorrent client / streaming client!"
            except Exception as e:
                return False, f"Failed to open magnet link: {e}"
        return False, "Please open the magnet link in your torrent client."

    # 2. Extract and download remote subtitle file if available
    subtitle_path: Optional[str] = None
    subtitles_raw = cached_stream.headers.get("X-Subtitles") or cached_stream.headers.get("subtitles_json")
    if subtitles_raw:
        try:
            subs = json.loads(subtitles_raw)
            if isinstance(subs, list) and subs:
                first_sub = subs[0]
                sub_url = first_sub.get("file") or first_sub.get("url")
                if sub_url and sub_url.startswith("http"):
                    try:
                        with httpx.Client(timeout=8.0, verify=False) as client:
                            resp = client.get(sub_url)
                            if resp.status_code == 200:
                                ext = ".vtt" if ".vtt" in sub_url else ".srt"
                                temp_sub = Path(tempfile.gettempdir()) / f"ripper_sub_{os.getpid()}{ext}"
                                temp_sub.write_text(resp.text, encoding="utf-8", errors="replace")
                                subtitle_path = str(temp_sub)
                    except Exception as e:
                        logger.debug("Failed to download subtitle %s: %s", sub_url, e)
        except Exception:
            pass

    # 3. Detect installed player and construct custom header invocation
    players = detect_available_players()
    if players:
        player_name, player_bin = players[0]
        referer = cached_stream.headers.get("Referer", "")
        user_agent = cached_stream.headers.get("User-Agent", "")

        cmd = [player_bin, direct_url]

        # Player-specific HTTP header arguments
        if "MPV" in player_name.upper():
            if user_agent:
                cmd.append(f'--user-agent={user_agent}')
            if referer:
                cmd.append(f'--referrer={referer}')
            if subtitle_path:
                cmd.append(f'--sub-file={subtitle_path}')
        elif "VLC" in player_name.upper():
            if user_agent:
                cmd.append(f'--http-user-agent={user_agent}')
            if referer:
                cmd.append(f'--http-referrer={referer}')
            if subtitle_path:
                cmd.append(f'--sub-file={subtitle_path}')
        elif "POTPLAYER" in player_name.upper():
            # PotPlayer handles headers and subtitles via command line switches
            if subtitle_path:
                cmd.append(f'/sub="{subtitle_path}"')
            if user_agent:
                cmd.append(f'/user_agent="{user_agent}"')
            if referer:
                cmd.append(f'/referer="{referer}"')

        try:
            save_playback_resume_state(direct_url, title=title, subtitle_path=subtitle_path)
            subprocess.Popen(cmd)
            sub_badge = f" [Subtitles: {os.path.basename(subtitle_path)}]" if subtitle_path else ""
            return True, f"🚀 Streaming live in {player_name} ({os.path.basename(player_bin)}){sub_badge}!"
        except Exception as e:
            logger.debug("Player custom launch failed, triggering auto-healer: %s", e)
            from ripper.ripperdb.self_healing import get_autonomous_healer
            healer = get_autonomous_healer()
            return healer.heal_player_failure(
                failed_player_name=player_name,
                direct_url=direct_url,
                headers=cached_stream.headers,
                subtitle_path=subtitle_path,
                title=title,
            )

    # 4. Standard fallback launcher
    ok, msg = launch_video_stream_in_player(
        direct_url,
        subtitle_path=subtitle_path,
        headers=cached_stream.headers,
        title=title,
    )
    if not ok:
        from ripper.ripperdb.self_healing import get_autonomous_healer
        healer = get_autonomous_healer()
        return healer.heal_player_failure(
            failed_player_name="default",
            direct_url=direct_url,
            headers=cached_stream.headers,
            subtitle_path=subtitle_path,
            title=title,
        )
    return ok, msg



def download_stream(
    cached_stream: CachedStream,
    title: str = "Media Download",
    output_dir: Optional[str] = None,
) -> bool:
    """
    Downloads a stream link via ripper's 8-thread resumable chunk downloader,
    or hands off magnet link to aria2c / default client.
    """
    direct_url = cached_stream.direct_url
    if not direct_url:
        console.print("[bold red]❌ Cannot download: Direct URL is empty.[/bold red]")
        return False

    # 1. Magnet link download
    if direct_url.startswith("magnet:?"):
        console.print("[bold cyan]🧲 Magnet Link Detected[/bold cyan]")
        # Check if aria2c is available
        import shutil
        aria2_bin = shutil.which("aria2c")
        if aria2_bin:
            dest = output_dir or os.getcwd()
            console.print(f"[bold green]⚡ Launching aria2c BitTorrent engine...[/bold green]")
            cmd = [aria2_bin, "--seed-time=0", f"--dir={dest}", direct_url]
            try:
                subprocess.Popen(cmd)
                return True
            except Exception as e:
                logger.debug("aria2c execution failed: %s", e)

        # Fallback to system default
        if sys.platform == "win32":
            try:
                os.startfile(direct_url)
                console.print("[bold green]✔ Magnet opened in default BitTorrent client.[/bold green]")
                return True
            except Exception as e:
                console.print(f"[bold red]❌ Failed to open magnet: {e}[/bold red]")
                return False
        return False

    # 2. Direct HTTP / HLS / MP4 chunk download
    clean_name = sanitize_filename(f"{title}.mp4")
    dest_dir = output_dir or os.getcwd()

    console.print(f"\n[bold cyan]📥 Starting High-Speed 8-Thread Resumable Download:[/bold cyan] [bold white]{clean_name}[/bold white]")
    console.print(f"[dim]Destination: {dest_dir}[/dim]\n")

    try:
        dest_path = Path(dest_dir)
        ref = cached_stream.headers.get("Referer", "") if cached_stream.headers else ""
        coro = download_file_fast(
            direct_url=direct_url,
            output_directory=dest_path,
            custom_filename=clean_name,
            num_threads=8,
            referer=ref,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                res = executor.submit(asyncio.run, coro).result()
        else:
            res = asyncio.run(coro)

        return res is not None
    except Exception as e:
        console.print(f"[bold red]❌ Download engine error: {e}[/bold red]")
        try:
            from ripper.ripperdb.self_healing import get_autonomous_healer
            healer = get_autonomous_healer()
            cat, rule, act, desc, tier = healer.diagnose_error(str(e), context={"url": direct_url, "title": title})
            healer.journal.record_incident(
                category=cat,
                rule_name=rule,
                error_str=str(e),
                action_taken=act,
                success=False,
                duration_ms=2.0,
                tier=tier,
                metadata={"title": title, "url": direct_url[:100]},
            )
            console.print(f"[dim yellow]🛡️ Healer Diagnosis: {desc}[/dim yellow]")
        except Exception:
            pass
        return False



def format_stream_summary(cached_stream: CachedStream, item: Optional[ReleaseItem] = None) -> Panel:
    """Renders a Rich terminal panel summarizing the resolved stream."""
    title = item.raw_title if item else "Resolved Stream"
    quality = cached_stream.quality or (item.resolution if item else "1080p")
    is_direct = getattr(cached_stream, "is_direct", True)
    stream_type = "Direct Playable CDN" if is_direct and not cached_stream.direct_url.startswith("magnet:") else ("BitTorrent Swarm Magnet" if cached_stream.direct_url.startswith("magnet:") else "Web Embed Player")

    summary_text = (
        f" [bold white]Title:[/bold white] [bold bright_cyan]{title}[/bold bright_cyan]\n"
        f" [bold white]Resolution:[/bold white] [bold bright_green]{quality.upper()}[/bold bright_green]  [dim]|[/dim]  "
        f" [bold white]Type:[/bold white] [yellow]{stream_type}[/yellow]  [dim]|[/dim]  "
        f" [bold white]Stream ID:[/bold white] [dim]{cached_stream.id}[/dim]\n"
        f" [bold white]Stream Link:[/bold white] [bright_white]{cached_stream.direct_url[:85]}...[/bright_white]\n"
    )

    if cached_stream.headers:
        hdr_items = [f"{k}: {v[:30]}..." if len(v) > 30 else f"{k}: {v}" for k, v in cached_stream.headers.items() if k not in ("X-Subtitles", "subtitles_json")]
        if hdr_items:
            summary_text += f" [bold white]Headers:[/bold white] [dim]{' | '.join(hdr_items)}[/dim]\n"

    return Panel(
        summary_text.strip(),
        title="[bold green]🎬 STREAM READY[/bold green]",
        border_style="bright_green",
        box=box.ROUNDED,
    )
