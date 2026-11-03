"""
Rich visual UI and terminal rendering for unshorten-cli (Enterprise & Pro Edition).
Features:
- Perfectly aligned, compact terminal tables (auto-fits 80-100 col terminals without wrapping)
- Cyberpunk styled color palettes
- Clean server cards and direct stream links
"""

import sys
import os

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from typing import List, Dict, Any
from collections import defaultdict
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich import box

from .models import UnshortenResult, HopInfo, SafetyReport, ServerMirror

console = Console(force_terminal=True, legacy_windows=False)


def format_bytes(size_bytes: int) -> str:
    """Format integer bytes into clean human-readable units."""
    if not size_bytes or size_bytes <= 0:
        return "Unknown size"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def display_ripper_cockpit_banner(player_name="POTPLAYER", proxy_status="127.0.0.1:5055 (IDLE)", radar_count=62):
    """Render the God-Mode Ripper dual-column Cockpit Header."""
    header_text = (
        "[bold cyan]██████╗ ██╗██████╗ ██████╗ ███████╗██████╗[/bold cyan]   [bold white][ GOD-MODE V3.5 CORE ][/bold white]\n"
        "[bold cyan]██╔══██╗██║██╔══██╗██╔══██╗██╔════╝██╔══██╗[/bold cyan]   [dim]●[/dim] [bold bright_green]PROXY:[/bold bright_green] [cyan]" + str(proxy_status) + "[/cyan]\n"
        "[bold cyan]██████╔╝██║██████╔╝██████╔╝█████╗  ██████╔╝[/bold cyan]   [dim]●[/dim] [bold bright_green]DoH:[/bold bright_green] [yellow]CLOUDFLARE/GOOGLE [ON][/yellow]\n"
        "[bold cyan]██╔══██╗██║██╔═══╝ ██╔═══╝ ██╔══╝  ██╔══██╗[/bold cyan]   [dim]●[/dim] [bold bright_green]RADAR:[/bold bright_green] [green]" + str(radar_count) + " SITES HEALTHY[/green]\n"
        "[bold cyan]██║  ██║██║██║     ██║     ███████╗██║  ██║[/bold cyan]   [dim]●[/dim] [bold bright_green]PLAYER:[/bold bright_green] [bold bright_magenta]" + str(player_name) + " (DETECTED)[/bold bright_magenta]\n"
        "[bold cyan]╚═╝  ╚═╝╚═╝╚═╝     ╚═╝     ╚══════╝╚═╝  ╚═╝[/bold cyan]\n"
        "[dim bold white]⚡ Autonomous Stream Ripper, Ad-Bypass & Universal Link Unshortener Engine[/dim bold white]"
    )
    console.print(Panel(header_text, border_style="bright_magenta", box=box.ROUNDED))


def display_unshorten_banner():
    """Render Cyberpunk ASCII art header with dynamic engine badges."""
    display_ripper_cockpit_banner()


def get_status_style(status_code: int) -> str:
    """Get color style based on HTTP status."""
    if status_code in (200, 201, 206):
        return "bold green"
    elif status_code in (301, 308):
        return "bold yellow"
    elif status_code in (302, 303, 307):
        return "bold cyan"
    elif status_code >= 400:
        return "bold red"
    return "dim white"


def get_risk_style(risk_level: str) -> str:
    """Get color style for safety risk level."""
    if risk_level == "SAFE":
        return "bold green"
    elif risk_level == "LOW RISK":
        return "bold cyan"
    elif risk_level == "SUSPICIOUS":
        return "bold yellow"
    return "bold bright_red"


def render_unshorten_tree(result: UnshortenResult):
    """Render a visual hierarchical tree of all redirect hops."""
    root_text = Text.from_markup(f"[bold white]🌐 START: [/bold white][cyan]{result.original_url}[/cyan]")
    tree = Tree(root_text)

    current_node = tree
    for i, hop in enumerate(result.hops, 1):
        is_last = (i == len(result.hops))
        status_style = get_status_style(hop.status_code)

        label = Text()
        label.append(f"Hop {hop.hop_number} ", style="bold magenta")
        label.append(f"[{hop.redirect_type}] ", style="dim yellow")
        
        if hop.status_code > 0:
            label.append(f"HTTP {hop.status_code} ", style=status_style)
        
        if hop.latency_ms > 0:
            label.append(f"({hop.latency_ms:.0f}ms) ", style="dim")

        if is_last:
            if "Bot Challenge Wall" in hop.redirect_type or not result.is_success:
                label.append("\n🛡️ STOPPED AT BOT CHALLENGE WALL: ", style="bold red")
                label.append(hop.url, style="bold red underline")
            else:
                label.append("\n🎯 FINAL DIRECT ENDPOINT: ", style="bold green")
                label.append(hop.url, style="bold bright_white underline")
            if hop.content_type:
                label.append(f"\n   [Type: {hop.content_type}]", style="dim cyan")
            if hop.content_length and hop.content_length > 0:
                label.append(f" [Size: {format_bytes(hop.content_length)}]", style="dim green")
        else:
            label.append(f"\n↳ {hop.url}", style="white")

        if hop.extra_details:
            label.append(f" [dim italic]({hop.extra_details})[/dim italic]")

        current_node = current_node.add(label)

    console.print(tree)


def render_server_mirrors_table(mirrors: List[ServerMirror]):
    """Render table of extracted download servers and direct cloud streams."""
    table = Table(title="🚀 DETECTED DOWNLOAD SERVERS & DIRECT CLOUD STREAMS", box=box.ROUNDED)
    table.add_column("#", justify="right", style="bold cyan", width=4)
    table.add_column("Server / Option", style="bold yellow", width=22)
    table.add_column("Type", style="cyan", width=24)
    table.add_column("Direct Resolved Cloud Stream URL", style="bold green")

    for i, m in enumerate(mirrors, 1):
        resolved_url = m.direct_download_url if m.direct_download_url else m.intermediate_url
        table.add_row(
            str(i),
            m.label,
            f"[bold green]✔ {m.server_type}[/bold green]",
            resolved_url,
        )
    console.print(table)


def render_media_grid_summary(items: List[Any]):
    """Render categorized Episode & Quality Media Grid with direct download links."""
    grouped = defaultdict(list)
    for it in items:
        grouped[it.movie_name or "Download Options"].append(it)

    console.print(f"\n[bold green]🎬 RESOLVED MEDIA DOWNLOAD STREAMS ({len(items)} Items)[/bold green]\n")

    for movie_name, ep_items in grouped.items():
        ep_tree = Tree(f"[bold bright_magenta]📽️  {movie_name}[/bold bright_magenta]")
        for item in ep_items:
            quality_badge = f"[bold cyan][{item.codec} {item.quality}][/bold cyan]"
            audio_badge = f"[dim yellow]({item.audio_info})[/dim yellow]"
            size_badge = f"[bold bright_green][{item.size_str}][/bold bright_green]" if item.size_str else ""
            
            node_label = f"{quality_badge} {size_badge} {audio_badge}"
            item_node = ep_tree.add(node_label)
            
            if item.servers:
                for s_idx, s in enumerate(item.servers, 1):
                    s_stream = s.direct_download_url or s.intermediate_url
                    status_text = "[bold green]Direct Cloud Stream (R2/S3)[/bold green]" if s.direct_download_url else "[yellow]Landing Page[/yellow]"
                    item_node.add(f"[bold yellow]Server {s_idx} ({s.label}) [{status_text}]:[/bold yellow]\n↳ [bold bright_green]{s_stream}[/bold bright_green]")
            elif item.unshortened_landing_url:
                item_node.add(f"[bold yellow]Unshortened Landing Page:[/bold yellow]\n↳ [bold bright_green]{item.unshortened_landing_url}[/bold bright_green]")
            else:
                item_node.add(f"[dim]Original Link:[/dim] {item.short_link}")

        console.print(ep_tree)
        console.print()


def display_unshorten_summary(result: UnshortenResult):
    """Display detailed summary card with safety metrics and target information."""
    safety = result.safety
    risk_style = get_risk_style(safety.risk_level)

    # 1. Hop Tree
    console.print("\n[bold cyan]📡 REDIRECT CHAIN TRACE:[/bold cyan]")
    render_unshorten_tree(result)

    # 2. Server Mirrors (if found)
    if result.server_mirrors:
        console.print()
        render_server_mirrors_table(result.server_mirrors)

    # 3. Safety & Destination Card
    summary_table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
    summary_table.add_column("Key", style="bold white", width=22)
    summary_table.add_column("Value")

    summary_table.add_row("🎯 Final Direct URL:", f"[bold bright_green]{result.final_url}[/bold bright_green]")
    summary_table.add_row("🌐 Domain:", f"[bold cyan]{safety.domain}[/bold cyan]")
    summary_table.add_row("🔒 Protocol Security:", "[green]✔ HTTPS (Encrypted)[/green]" if safety.is_https else "[red]❌ Plain HTTP (Insecure)[/red]")
    summary_table.add_row("📦 Resource Type:", f"[bold yellow]{safety.mime_category}[/bold yellow]" + (f" ({safety.content_type})" if safety.content_type else ""))
    
    if safety.content_length_bytes > 0:
        summary_table.add_row("💾 File Size:", f"[cyan]{format_bytes(safety.content_length_bytes)}[/cyan]")

    summary_table.add_row("⏱️ Total Latency:", f"[dim]{result.total_time_ms:.1f} ms across {result.total_hops} hop(s)[/dim]")
    summary_table.add_row("🛡️ Safety Assessment:", f"[{risk_style}]{safety.risk_level} (Score: {safety.risk_score}/100)[/{risk_style}]")

    if safety.flags:
        flags_text = "\n".join([f" • [{risk_style}]{f}[/{risk_style}]" for f in safety.flags])
        summary_table.add_row("⚠️ Security Flags:", flags_text)

    console.print(Panel(summary_table, title="[bold green]FINAL DESTINATION & SECURITY REPORT[/bold green]", border_style="bright_blue", box=box.ROUNDED))

    if result.error_message:
        console.print(Panel(
            f"[bold red]⚠️ RESOLUTION STOPPED:[/bold red] [white]{result.error_message}[/white]\n"
            f"[dim]💡 Notice: This target domain enforces Cloudflare Turnstile / Bot Verification. Automated HTTP tools receive an HTTP 403 challenge page instead of the redirect stream. To access the true destination, open the link in a real desktop browser to solve the Turnstile challenge.[/dim]",
            title="[bold yellow]BOT VERIFICATION DETECTED[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        ))


def display_batch_summary_table(results: List[UnshortenResult]):
    """Display table of multiple unshortened URLs."""
    table = Table(title=f"📦 BATCH UNSHORTEN RESULTS ({len(results)} ITEMS)", box=box.ROUNDED)
    table.add_column("#", justify="right", style="bold cyan", width=4)
    table.add_column("Original Short URL", style="yellow")
    table.add_column("Hops", justify="center", style="magenta", width=6)
    table.add_column("Type", style="cyan", width=14)
    table.add_column("Risk", justify="center", width=12)
    table.add_column("Final Destination / Cloud URL", style="bold green")

    for i, r in enumerate(results, 1):
        risk_style = get_risk_style(r.safety.risk_level)
        table.add_row(
            str(i),
            r.original_url[:35] + ("..." if len(r.original_url) > 35 else ""),
            str(r.total_hops),
            r.safety.mime_category,
            f"[{risk_style}]{r.safety.risk_level}[/{risk_style}]",
            r.final_url,
        )

    console.print(table)

