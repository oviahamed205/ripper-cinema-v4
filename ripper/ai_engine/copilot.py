"""
ripper.ai_engine.copilot
~~~~~~~~~~~~~~~~~~~~~~~~

AI Copilot and Knowledge Engine for RIPPER.
Synchronizes the local K2-Horizon AI with all CLI commands, features,
and operational workflows.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()

# Comprehensive RIPPER System Knowledge Base
RIPPER_KNOWLEDGE = {
    "name": "RIPPER (Enterprise & God-Mode Edition)",
    "description": (
        "God-Mode Autonomous Stream & Media Ripper, Ad-Bypass & Link Unshortener. "
        "Built for ultra-fast media discovery, 1-click playback, stream ripping, and container decoding."
    ),
    "ai_engine": {
        "model": "K2-Horizon-1B (BF16 GGUF)",
        "role": (
            "Local neural intelligence running directly on your system (Zen 4 CPU + Intel Arc A770 GPU). "
            "Powers natural language query planning, GBNF-constrained JSON link parsing, and terminal assistance "
            "with 100% offline privacy and zero external API dependencies."
        ),
    },
    "features": [
        {
            "name": "🔍 Multi-Site Media Search",
            "flags": ["-s", "--search", "-S", "--site", "-q", "--quality", "--lang", "--year"],
            "description": "Searches across CineFreak, KMmovies, Katworld, VegaMovies, OlaMovies, and HDHub4u with resolution and language filtering.",
            "example": "ripper -s \"Interstellar\" -q 4k --lang hindi",
        },
        {
            "name": "⚡ 1-Click Instant Watch",
            "flags": ["-w", "--watch", "-r", "--resume", "-a", "--audio"],
            "description": "Unshortens link, resolves Cloudflare R2 / PixelDrain / GDrive direct mirrors, and launches PotPlayer or VLC in <1 second.",
            "example": "ripper -w \"https://cinefreak.net/movie-page\"",
        },
        {
            "name": "🔓 Universal Shortlink & Container Bypass",
            "flags": ["-b", "--bypass", "--cnl"],
            "description": "Bypasses 400+ ad-gates (GPLinks, Droplink, Rocklinks, OUO, Filecrypt, Keeplinks, DLC) via FastForward rules, V8 human emulation, and CNL crypto.",
            "example": "ripper -b \"https://gplinks.co/example\"",
        },
        {
            "name": "🌐 AnyStream Video Ripper",
            "flags": ["-as", "--anystream"],
            "description": "Universally extracts direct playable/downloadable .mp4, .mkv, or .m3u8 video streams from video hosts (StreamWish, FileLions, DoodStream, etc.).",
            "example": "ripper -as \"https://doodstream.com/e/example\"",
        },
        {
            "name": "🎬 Cinema Web Player",
            "flags": ["--player", "--web"],
            "description": "Launches a browser-based cinema web player with subtitle and audio track switching on http://127.0.0.1:5055/player.",
            "example": "ripper --player",
        },
        {
            "name": "🎯 Autonomous Hunter Suite",
            "flags": ["--hunt-site", "-hm", "--hunt-movie"],
            "description": "Site Hunter discovers & verifies new active streaming domains; Movie Hunter verifies releases across all active sites simultaneously.",
            "example": "ripper -hm \"Gladiator 2\"",
        },
        {
            "name": "🌈 Cinema Auto-Pilot (Audiophile & Video)",
            "flags": ["--hdr", "--atmos", "--remux"],
            "description": "Automatically prioritizes Dolby Vision / HDR10+, Dolby Atmos / TrueHD lossless audio, and pristine REMUX releases.",
            "example": "ripper -s \"Dune 2\" --hdr --atmos -w",
        },
        {
            "name": "📑 Subtitle Brain & Metadata",
            "flags": ["--sub-lang", "--no-subs", "--trailer", "--no-apis"],
            "description": "Auto-downloads subtitles via OpenSubtitles (e.g. en,hi), enriches release details with TMDB/OMDb, and launches YouTube trailers.",
            "example": "ripper -s \"Oppenheimer\" --sub-lang en,hi -tr",
        },
        {
            "name": "⚡ Click'n'Load Daemon",
            "flags": ["--cnl"],
            "description": "Starts local Click'n'Load port 9666 daemon to capture DLC and encrypted links directly from browser download buttons.",
            "example": "ripper --cnl",
        },
        {
            "name": "🧠 Local AI Telemetry & Copilot",
            "flags": ["--ai-status", "--ai-parse", "--ai", "--ai-chat"],
            "description": "Inspects K2-Horizon neural model telemetry, executes AI query planning, or runs conversational terminal copilot.",
            "example": "ripper --ai-status",
        },
        {
            "name": "🧬 Simulation & Diagnostics",
            "flags": ["-sim", "--simulate"],
            "description": "Executes 100-run iterative simulation and comprehensive self-diagnostic test across all subsystems.",
            "example": "ripper --simulate",
        },
        {
            "name": "🖥️ Interactive Visual Dashboard",
            "flags": ["-i", "--interactive"],
            "description": "Full-featured Rich terminal dashboard with 1-click menus, live telemetry, history, and watchlist.",
            "example": "ripper -i",
        },
    ],
}


@dataclass
class AICopilotResponse:
    query: str
    answer: str
    suggested_command: Optional[str] = None
    action_type: str = "info"  # "search", "watch", "bypass", "stream", "info", "help"
    action_params: Dict[str, Any] = field(default_factory=dict)


def answer_user_query(user_query: str) -> AICopilotResponse:
    """
    Core AI knowledge reasoner that maps user queries to RIPPER features,
    explanations, and exact CLI commands.
    """
    q = user_query.strip()
    q_lower = q.lower()

    # 1. "What can you do?" / "What can this AI do?" / "Help" / "Capabilities"
    if any(k in q_lower for k in [
        "what can you do", "what can this ai do", "what can i do",
        "features", "capabilities", "options", "what do you do",
        "how does this work", "who are you", "help me", "commands",
    ]):
        ans = (
            "**I am your local RIPPER AI Copilot**, powered by **K2-Horizon 1B** running privately on your hardware!\n\n"
            "Here is everything you and I can do together:\n\n"
            "1. **🔍 Search & Stream Movies/Series:** Ask me or RIPPER for any movie or TV show. I parse titles, seasons, 4K/1080p resolutions, and audio tracks.\n"
            "2. **⚡ 1-Click Instant Watch (`-w`):** Paste any URL or search title to resolve the fastest cloud mirror (R2, PixelDrain) and launch PotPlayer in <1s.\n"
            "3. **🔓 Universal Bypass (`-b`):** Bypass over 400+ shorteners and ad-gates (GPLinks, Droplink, Rocklinks, Filecrypt, Keeplinks, DLC, Click'n'Load).\n"
            "4. **🌐 AnyStream Ripper (`-as`):** Rip playable direct video streams (.mkv/.mp4/.m3u8) from video embed hosts (StreamWish, FileLions, DoodStream, etc.).\n"
            "5. **🎬 Cinema Web Player (`--player`):** Stream in your web browser at `http://127.0.0.1:5055/player`.\n"
            "6. **🎯 Autonomous Hunters (`--hunt-site`, `-hm`):** Automatically discover new active streaming domains and verify releases across all sites.\n"
            "7. **🌈 Cinema Auto-Pilot:** Prioritize `--hdr` (Dolby Vision), `--atmos` (Dolby Atmos), and `--remux` (lossless BluRay).\n"
            "8. **📑 Subtitles & Audio:** Auto-download subtitles (`--sub-lang en,hi`) and auto-switch audio language (`--lang hindi` / `-a hindi`).\n"
            "9. **⚡ Click'n'Load Daemon (`--cnl`):** Capture browser DLC containers on port 9666.\n"
            "10. **🧠 Local AI Telemetry (`--ai-status`):** Check my status, memory usage, and hardware acceleration."
        )
        return AICopilotResponse(
            query=user_query,
            answer=ans,
            suggested_command="ripper -i",
            action_type="help",
        )

    # 2. Shortlink / Ad-gate Bypass Request
    if any(k in q_lower for k in ["bypass", "unshorten", "shortlink", "adgate", "gplinks", "droplink", "filecrypt"]):
        # Extract URL if present
        url_m = re.search(r"https?://\S+", q)
        if url_m:
            target_url = url_m.group(0)
            return AICopilotResponse(
                query=user_query,
                answer=f"I detected a shortlink/container bypass request for `{target_url}`. RIPPER will apply universal de-obfuscation and human emulation.",
                suggested_command=f'ripper -b "{target_url}"',
                action_type="bypass",
                action_params={"url": target_url},
            )
        return AICopilotResponse(
            query=user_query,
            answer=(
                "To bypass any shortlink, container, or ad-gate, use the `--bypass` / `-b` flag with the URL.\n"
                "RIPPER supports 400+ services including GPLinks, Droplink, Rocklinks, OUO, Filecrypt, Keeplinks, and DLC."
            ),
            suggested_command='ripper -b "https://shortener-url.com/xyz"',
            action_type="bypass",
        )

    # 3. Video Stream Ripping / AnyStream
    if any(k in q_lower for k in ["rip", "anystream", "streamwish", "filelions", "doodstream", "embed", "m3u8", "extract video"]):
        url_m = re.search(r"https?://\S+", q)
        if url_m:
            target_url = url_m.group(0)
            return AICopilotResponse(
                query=user_query,
                answer=f"I detected an AnyStream video extraction request for `{target_url}`. RIPPER will extract the direct playable video stream.",
                suggested_command=f'ripper -as "{target_url}"',
                action_type="stream",
                action_params={"url": target_url},
            )
        return AICopilotResponse(
            query=user_query,
            answer=(
                "To universally extract direct playable video streams (.mp4 / .mkv / .m3u8) from any video embed host, "
                "use the `--anystream` / `-as` flag."
            ),
            suggested_command='ripper -as "https://doodstream.com/e/example"',
            action_type="stream",
        )

    # 4. Web Player Request
    if any(k in q_lower for k in ["web player", "browser player", "cinema player", "watch in browser"]):
        return AICopilotResponse(
            query=user_query,
            answer="You can launch the built-in Cinema Web Player on `http://127.0.0.1:5055/player` to stream directly in your browser.",
            suggested_command="ripper --player",
            action_type="player",
        )

    # 5. Hunter Requests
    if any(k in q_lower for k in ["hunt", "discover sites", "new sites", "movie hunter"]):
        return AICopilotResponse(
            query=user_query,
            answer=(
                "RIPPER includes the Autonomous Hunter suite:\n"
                "• `--hunt-site`: Scours the web to discover and verify new live streaming domains.\n"
                "• `-hm \"<query>\"`: Hunts and verifies releases across ALL active sites simultaneously."
            ),
            suggested_command='ripper -hm "Dune 2"',
            action_type="hunter",
        )

    # 6. Click'n'Load Request
    if any(k in q_lower for k in ["cnl", "click n load", "clicknload", "port 9666", "dlc"]):
        return AICopilotResponse(
            query=user_query,
            answer="To start the local Click'n'Load daemon on port 9666 and capture encrypted browser downloads, run `ripper --cnl`.",
            suggested_command="ripper --cnl",
            action_type="cnl",
        )

    # 7. Media Play / Search Query (e.g. "play breaking bad s02e05 in 1080p", "download inception")
    from . import parse_query_ai
    plan = parse_query_ai(q)
    watch_flag = "-w" if any(k in q_lower for k in ["play", "watch", "stream"]) else ""
    cmd_parts = ["ripper", f'-s "{plan.cleaned_title}"']
    if plan.quality_target != "ANY":
        cmd_parts.append(f"-q {plan.quality_target.lower()}")
    if plan.audio_preference:
        cmd_parts.append(f"--lang {plan.audio_preference.lower()}")
    if plan.year:
        cmd_parts.append(f"--year {plan.year}")
    if watch_flag:
        cmd_parts.append(watch_flag)

    suggested = " ".join(cmd_parts)
    ans = (
        f"I analyzed your request using my neural query planner:\n"
        f"• **Target Title:** {plan.cleaned_title}\n"
        f"• **Type:** {'TV Series' if plan.media_type == 'tv' else 'Movie'}\n"
        f"• **Coordinates:** " + (f"S{plan.season:02d}E{plan.episode:02d}" if plan.season else "Full Feature") + "\n"
        f"• **Target Quality:** {plan.quality_target}\n"
        f"• **Audio:** {plan.audio_preference or 'Original / Any'}\n\n"
        f"I formulated the exact command for you below."
    )

    return AICopilotResponse(
        query=user_query,
        answer=ans,
        suggested_command=suggested,
        action_type="search",
        action_params={"plan": plan.to_dict()},
    )


def display_copilot_response(resp: AICopilotResponse) -> None:
    """Renders formatted copilot response with Rich."""
    content = f"[bold white]{resp.answer}[/bold white]"
    if resp.suggested_command:
        content += f"\n\n[bold green]💡 Recommended CLI Command:[/bold green]\n[bold yellow]{resp.suggested_command}[/bold yellow]"

    panel = Panel(
        content,
        title="[bold cyan]🧠 RIPPER AI Copilot (K2-Horizon)[/bold cyan]",
        subtitle="[dim]Powered by local GGUF neural inference[/dim]",
        border_style="bright_blue",
        box=box.ROUNDED,
    )
    console.print(panel)


def launch_ai_chat() -> None:
    """
    Interactive multi-turn AI Copilot chat terminal session.
    """
    console.print("\n[bold cyan]══════════════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold bright_cyan]  🧠 RIPPER AI COPILOT INTERACTIVE CONVERSATION (K2-Horizon 1B)[/bold bright_cyan]")
    console.print("[dim]  Ask any question about RIPPER, features, commands, or media workflows.[/dim]")
    console.print("[dim]  Type 'exit', 'quit', or '0' to return to the dashboard.[/dim]")
    console.print("[bold cyan]══════════════════════════════════════════════════════════════════════[/bold cyan]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold bright_yellow]Ask AI[/bold bright_yellow]").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "0", "back"):
                console.print("[dim]Returning to main dashboard...[/dim]\n")
                break

            resp = answer_user_query(user_input)
            display_copilot_response(resp)

            if resp.suggested_command and resp.action_type in ("search", "watch", "bypass", "stream"):
                run_now = Prompt.ask(
                    "[bold yellow]Would you like to execute this command now?[/bold yellow]",
                    choices=["y", "n"],
                    default="y",
                )
                if run_now.lower() == "y":
                    import subprocess
                    console.print(f"[bold green]▶ Running: {resp.suggested_command}[/bold green]\n")
                    subprocess.run(resp.suggested_command, shell=True)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]AI Chat session closed.[/dim]")
            break
