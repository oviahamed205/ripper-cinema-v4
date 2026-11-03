"""
Command-line interface (CLI) entrypoint for unshorten-cli (Enterprise & Pro Edition).
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import asyncio
from pathlib import Path
from typing import List, Optional
import click
import httpx
from rich.table import Table
from rich import box

from . import _IMPORT_ERRORS
from .resolver import unshorten_url, DEFAULT_USER_AGENT
from .batch import batch_unshorten_urls, parse_urls_from_file_path, export_results_to_file
from .media import extract_media_items_from_html, deep_resolve_media_items
from .ui import console, display_unshorten_summary, display_batch_summary_table, render_media_grid_summary
from .interactive import launch_interactive_unshortener, run_one_click_instant_watch, handle_search_flow, handle_global_search_flow
from .search import execute_multi_site_search


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("-gs", "--global-search", "global_search_query", type=str, default=None, help="🌍 Global Federated Search across 736+ FMHY providers, torrents & indexers.")
@click.option("--crawl-fmhy", is_flag=True, help="🕷️ Deep-crawl https://fmhy.net/video live, extract all updated sites & mirrors without missing a single link, and show diff.")
@click.option("--sync-fmhy", is_flag=True, help="🔄 Synchronize local database with FMHY live provider mirrors.")
@click.option("--force-sync", is_flag=True, help="⚡ Force clean re-sync of FMHY video provider registry.")
@click.option("--ripperdb-stats", is_flag=True, help="📊 Display RipperDB database, mirror and cache telemetry statistics.")
@click.option("--season", type=int, default=None, help="Filter TV series releases by season number.")
@click.option("--episode", type=int, default=None, help="Filter TV series releases by episode number.")
@click.option("--min-quality", type=str, default=None, help="Filter releases by minimum resolution (e.g. 720p, 1080p, 4k).")
@click.option("-dl", "--download", "download_flag", is_flag=True, help="📥 Resumable Download: auto-resolve and download top stream release.")
@click.option("--hunt-site", is_flag=True, help="🌍 Autonomous Site Hunter: discover, verify & integrate new live movie sites.")
@click.option("--hunt-movie", "-hm", "hunt_movie_query", type=str, default=None, help="🎯 Autonomous Movie Hunter: search & verify releases across ALL discovered sites.")
@click.option("-as", "--anystream", "any_stream_url", type=str, default=None, help="🌐 AnyStream: Universally extract direct playable/downloadable video streams from ANY link.")
@click.option("--player", "--web", "launch_web_player", is_flag=True, help="🌐 Launch Cinema Web Player directly in your browser on http://127.0.0.1:5055/player.")
@click.option("-i", "--interactive", is_flag=True, help="Launch interactive visual terminal dashboard.")
@click.option("-s", "--search", "search_query", type=str, help="🔍 Search movies & series by name across CineFreak, KMmovies, Katworld, VegaMovies, OlaMovies, HDHub4u.")
@click.option("-S", "--site", "target_site", type=str, default=None, help="Search only specific site(s). Comma-separated: cinefreak,kmmovies,katmoviehd,vegamovies,olamovies,hdhub4u. Default: all")
@click.option("--lang", "language_filter", type=str, default=None, help="Filter results by language: hindi,tamil,telugu,malayalam,bengali,english,dual,multi")
@click.option("--year", "year_filter", type=str, default=None, help="Filter search results by release year (e.g. 2024).")
@click.option("-q", "--quality", "quality_filter", type=str, default=None, help="Filter movie search results by resolution: 4k, 2160p, 1080p, 720p, 480p.")
@click.option("--tmdb-key", "tmdb_api_key", type=str, default=None, help="Save TMDB API key to ~/.ripper/config.json.")
@click.option("--omdb-key", "omdb_api_key", type=str, default=None, help="Save OMDb API key to ~/.ripper/config.json.")
@click.option("--youtube-key", "youtube_api_key", type=str, default=None, help="Save YouTube API key to ~/.ripper/config.json.")
@click.option("--opensubtitles-key", "opensubtitles_api_key", type=str, default=None, help="Save OpenSubtitles API key to ~/.ripper/config.json.")
@click.option("--sub-lang", "sub_languages", type=str, default="en,hi", help="Subtitle languages to auto-download (default: en,hi).")
@click.option("--no-subs", "no_subs", is_flag=True, help="Skip subtitle auto-downloading.")
@click.option("--trailer", "-tr", "show_trailer", is_flag=True, help="Open official movie trailer in browser.")
@click.option("--no-apis", "no_apis", is_flag=True, help="Skip TMDB/TVmaze/AniList API metadata brain layer.")
@click.option("--export-search", "export_search_path", type=click.Path(), default=None, help="Export search results to file (.json, .csv, .md)")
@click.option("-w", "--watch", is_flag=True, help="⚡ 1-Click Instant Watch: auto-resolve Cloud [Resumable] and launch PotPlayer.")
@click.option("-a", "--audio", "audio_language", type=str, default=None, help="🔊 Smart Audio Track Selector: auto-select audio language in player (e.g. hindi, english, tamil).")
@click.option("-f", "--file", "file_path", type=click.Path(exists=True), help="Load and unshorten list of URLs from file (.txt, .csv, .md).")
@click.option("-o", "--output", "output_path", type=click.Path(), help="Export resolved results to file (.json, .csv, .md).")
@click.option("-p", "--paste", "paste_content", type=str, help="Raw HTML snippet containing download-links-div / episode-grid.")
@click.option("--media", is_flag=True, help="Extract & deep-unshorten media/episode grid from page URL or pasted HTML.")
@click.option("--login-olamovies", is_flag=True, help="🔐 Launch Chrome to log into OlaMovies, capture session token, and auto-close.")
@click.option("-r", "--resume", is_flag=True, help="▶ Resume Playback: 1-click resume last watched movie or episode in PotPlayer.")
@click.option("--hdr", is_flag=True, help="🌈 Auto-Pilot Cinema: prioritize Dolby Vision & HDR10+ releases.")
@click.option("--atmos", is_flag=True, help="🔊 Auto-Pilot Cinema: prioritize Dolby Atmos & TrueHD audio releases.")
@click.option("--remux", is_flag=True, help="💎 Auto-Pilot Cinema: prioritize pristine lossless REMUX releases.")
@click.option("--debrid-key", "debrid_key", type=str, default=None, help="Save Real-Debrid API key to ~/.ripper/config.json.")
@click.option("--no-doh", is_flag=True, help="Disable DNS over HTTPS ISP-unblocker.")
@click.option("--simulate", "-sim", is_flag=True, help="🧬 Run 100-Run Iterative Simulation & System Diagnostic Suite.")
@click.option("-c", "--concurrency", default=10, help="Number of parallel worker streams for batch mode (default: 10).")
@click.option("-m", "--max-hops", default=15, help="Maximum number of redirect hops before stopping (default: 15).")
@click.option("-t", "--timeout", default=5.0, help="HTTP connection timeout in seconds (default: 5.0s).")
@click.option("--json", "json_output", is_flag=True, help="Output results in machine-readable raw JSON format.")
@click.option("--deep", is_flag=True, help="Include detailed HTTP headers and security breakdown for every hop.")
@click.option("--bypass", "-b", "bypass_url_target", type=str, default=None, help="🔓 Universal Shortlink & Container Bypass (GPLinks, Filecrypt, Droplink, Rocklinks, Keeplinks).")
@click.option("--cnl", is_flag=True, help="⚡ Start local Click'n'Load (Port 9666) listener daemon.")
@click.option("--ai-status", "show_ai_status", is_flag=True, help="🧠 Display local AI Engine (K2-Horizon) status & acceleration telemetry.")
@click.option("--ai-health", "show_ai_health", is_flag=True, help="🛡️ Display AI Autonomous Self-Healing Watchdog health & auto-remediation metrics.")
@click.option("--ai-parse", "ai_parse_query", type=str, default=None, help="🧠 Execute AI query planner on natural language prompt.")
@click.option("--ai", "-ai", "ai_copilot_prompt", type=str, default=None, is_flag=False, flag_value="CHAT_MODE", help="🧠 RIPPER AI Copilot: Ask any question about RIPPER, features, options, or get workflow guidance.")
@click.option("--ai-chat", "launch_chat", is_flag=True, help="🧠 Launch interactive terminal conversation with local K2-Horizon AI Copilot.")
@click.option("--doctor", "run_doctor", is_flag=True, help="🩺 Comprehensive Preflight System Doctor: validates OS, DoH network, player binaries, DB integrity, and SSL.")
@click.option("--heal", "run_heal", is_flag=True, help="🛡️ Trigger active system self-healing (repairs DB WAL, probes mirrors, cleans temp locks).")
@click.option("--healer-stats", "show_healer_stats", is_flag=True, help="📊 Display Autonomous Self-Healing & FixNet cumulative learning statistics.")
@click.option("--bandit-stats", "show_bandit_stats", is_flag=True, help="🎰 Display Bayesian Multi-Armed Bandit (Thompson Sampling) CDN & Mirror Router posteriors.")
@click.option("--predict-hops", "predict_hops_url", type=str, default=None, help="🔮 Predict downstream redirect hop chain via First-Order Markov Graph & pre-warm DoH DNS.")
@click.option("--deobfuscate", "deobfuscate_input", type=str, default=None, help="🧬 Execute 7-Pass Symbolic & AST JavaScript Deobfuscator on JS snippet or file path.")
@click.option("--omega-bench", "run_omega_bench", is_flag=True, help="⚡ Run v4.0 Omega Multi-Engine Micro-Benchmark Suite (FastAccel, Packer, AST, Bandit, Markov).")
@click.option("--mcp", "run_mcp_server", is_flag=True, help="🤖 Start Model Context Protocol (MCP) JSON-RPC 2.0 server over stdio for AI agents.")
@click.argument("urls", nargs=-1, required=False)
def main(

    urls: tuple,
    hunt_site: bool,
    hunt_movie_query: Optional[str],
    any_stream_url: Optional[str],
    launch_web_player: bool,
    interactive: bool,
    search_query: Optional[str],
    target_site: Optional[str],
    language_filter: Optional[str],
    year_filter: Optional[str],
    quality_filter: Optional[str],
    tmdb_api_key: Optional[str],
    omdb_api_key: Optional[str],
    youtube_api_key: Optional[str],
    opensubtitles_api_key: Optional[str],
    sub_languages: str,
    no_subs: bool,
    show_trailer: bool,
    no_apis: bool,
    export_search_path: Optional[str],
    watch: bool,
    audio_language: Optional[str],
    file_path: Optional[str],
    output_path: Optional[str],
    paste_content: Optional[str],
    media: bool,
    login_olamovies: bool,
    resume: bool,
    hdr: bool,
    atmos: bool,
    remux: bool,
    debrid_key: Optional[str],
    no_doh: bool,
    simulate: bool,
    concurrency: int,
    max_hops: int,
    timeout: float,
    json_output: bool,
    deep: bool,
    bypass_url_target: Optional[str] = None,
    cnl: bool = False,
    show_ai_status: bool = False,
    show_ai_health: bool = False,
    ai_parse_query: Optional[str] = None,
    ai_copilot_prompt: Optional[str] = None,
    launch_chat: bool = False,
    global_search_query: Optional[str] = None,
    crawl_fmhy: bool = False,
    sync_fmhy: bool = False,
    force_sync: bool = False,
    ripperdb_stats: bool = False,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    min_quality: Optional[str] = None,
    download_flag: bool = False,
    run_doctor: bool = False,
    run_heal: bool = False,
    show_healer_stats: bool = False,
    show_bandit_stats: bool = False,
    predict_hops_url: Optional[str] = None,
    deobfuscate_input: Optional[str] = None,
    run_omega_bench: bool = False,
    run_mcp_server: bool = False,
):

    """
    RIPPER: God-Mode Autonomous Stream & Media Ripper, Ad-Bypass & Link Unshortener.

    Examples:

      ripper --hunt-site

      ripper -hm "Inception"

      ripper -s "Spider-Man" --site vegamovies

      ripper -as "https://doodstream.com/e/example"

      ripper --watch "https://cinefreak.net/movie-url"

      ripper (launches interactive visual dashboard)
    """
    if _IMPORT_ERRORS:
        console.print("[bold yellow]⚠️ Warning: Some optional modules could not be loaded:[/bold yellow]")
        for err in _IMPORT_ERRORS:
            console.print(f"  [dim]• {err}[/dim]")
        console.print("[dim]Run 'pip install -e .' to ensure all optional dependencies are active.[/dim]\n")

    # Set API Keys if passed
    from .config import set_config_value
    if tmdb_api_key:
        set_config_value("tmdb_api_key", tmdb_api_key.strip())
        console.print(f"[bold green]✔ Saved TMDB API Key to ~/.ripper/config.json[/bold green]\n")
    if omdb_api_key:
        set_config_value("omdb_api_key", omdb_api_key.strip())
        console.print(f"[bold green]✔ Saved OMDb API Key to ~/.ripper/config.json[/bold green]\n")
    if youtube_api_key:
        set_config_value("youtube_api_key", youtube_api_key.strip())
        console.print(f"[bold green]✔ Saved YouTube API Key to ~/.ripper/config.json[/bold green]\n")
    if opensubtitles_api_key:
        set_config_value("opensubtitles_api_key", opensubtitles_api_key.strip())
        console.print(f"[bold green]✔ Saved OpenSubtitles API Key to ~/.ripper/config.json[/bold green]\n")
    if debrid_key:
        from .debrid import save_debrid_key
        save_debrid_key(debrid_key)
        console.print(f"[bold green]✔ Saved Real-Debrid API Key to ~/.ripper/config.json[/bold green]\n")
    if no_doh:
        from .doh import set_doh_enabled
        set_doh_enabled(False)

    if show_ai_status:
        from .ai_engine import get_ai_status
        status = get_ai_status()
        console.print("[bold cyan]🧠 RIPPER Local AI Engine Telemetry[/bold cyan]")
        console.print(f"  [bold]Model:[/bold] {status.model_name}")
        console.print(f"  [bold]Architecture:[/bold] {status.architecture}")
        console.print(f"  [bold]Backend:[/bold] {status.backend.value}")
        console.print(f"  [bold]Status:[/bold] {'[green]ONLINE & READY[/green]' if status.is_ready else '[red]OFFLINE[/red]'}")
        console.print(f"  [bold]Path:[/bold] {status.model_path or 'Not loaded'}")
        if status.file_size_bytes:
            console.print(f"  [bold]Weight Size:[/bold] {status.file_size_bytes / (1024*1024):.1f} MB")
        return

    if show_ai_health:
        from .ai_engine.self_healing import WATCHDOG
        WATCHDOG.render_health_panel()
        try:
            from .healer_engine import get_global_watchdog, EnvironmentDoctor
            doc = EnvironmentDoctor()
            rep = doc.run_health_checks()
            console.print("\n[bold cyan]🩺 System Environment Doctor Telemetry[/bold cyan]")
            console.print(f"  [bold]Healthy:[/bold] {'[green]YES[/green]' if rep.healthy else '[red]NO[/red]'}")
            console.print(f"  [bold]DNS Resolves:[/bold] {'[green]OK[/green]' if rep.dns_resolves else '[red]FAILED[/red]'}")
            console.print(f"  [bold]TCP Network:[/bold] {'[green]OK[/green]' if rep.network_available else '[red]FAILED[/red]'}")
            console.print(f"  [bold]SSL Context:[/bold] {'[green]OK[/green]' if rep.ssl_valid else '[red]FAILED[/red]'}")
            console.print(f"  [bold]Local AI GGUF:[/bold] {'[green]ACCESSIBLE[/green]' if rep.local_ai_accessible else '[yellow]OFFLINE / UNMOUNTED[/yellow]'}")
            h_wd = get_global_watchdog()
            console.print(f"  [bold]Healer Interceptions:[/bold] {h_wd.remediation_counter}")
        except Exception as e:
            console.print(f"[dim]Environment Doctor offline: {e}[/dim]")
        return

    if run_doctor:
        from .ripperdb.self_healing import get_autonomous_healer
        healer = get_autonomous_healer()
        report = healer.run_system_doctor()
        doc_table = Table(title="[bold cyan]🩺 RIPPER System Doctor Preflight Diagnostics[/bold cyan]", box=box.ROUNDED, border_style="cyan")
        doc_table.add_column("Subsystem", style="bold white")
        doc_table.add_column("Status", style="bold")
        doc_table.add_column("Details", style="dim")

        checks = report.get("checks", {})
        for name, c in checks.items():
            st = c.get("status", "UNKNOWN")
            color = "green" if st == "PASS" else ("yellow" if st == "OPTIONAL" else "red")
            details = ", ".join(f"{k}: {v}" for k, v in c.items() if k != "status")
            doc_table.add_row(name.replace("_", " ").title(), f"[{color}]{st}[/{color}]", details[:80])

        console.print(doc_table)
        overall = report.get("overall_healthy", False)
        verdict = "[bold green]✔ SYSTEM HEALTHY & PRODUCTION READY[/bold green]" if overall else "[bold yellow]⚠ SYSTEM HAS MINOR WARNINGS[/bold yellow]"
        console.print(f"\n{verdict}\n")
        return

    if run_heal:
        from .ripperdb.self_healing import get_autonomous_healer
        healer = get_autonomous_healer()
        console.print("[bold cyan]🛡️ Launching Autonomous Self-Healing Routine...[/bold cyan]")
        res = healer.trigger_full_healing()
        console.print(f"[bold green]✔ Self-healing complete in {res.get('duration_ms', 0)}ms[/bold green]")
        for act in res.get("actions_taken", []):
            console.print(f"  • [green]{act}[/green]")
        return

    if show_healer_stats:
        from .ripperdb.self_healing import get_autonomous_healer
        healer = get_autonomous_healer()
        summary = healer.journal.get_summary()
        stats_table = Table(title="[bold cyan]📊 Autonomous Self-Healing & FixNet Consensus Telemetry[/bold cyan]", box=box.ROUNDED, border_style="green")
        stats_table.add_column("Metric", style="bold white")
        stats_table.add_column("Value", style="bold bright_green")
        stats_table.add_row("Total Incidents Intercepted", str(summary.get("total_intercepted", 0)))
        stats_table.add_row("Auto-Healed & Remediated", str(summary.get("total_auto_healed", 0)))
        stats_table.add_row("Autonomy Success Rate", f"{summary.get('success_rate_pct', 100.0)}%")
        console.print(stats_table)

        cats = summary.get("category_breakdown", {})
        if cats:
            cat_table = Table(title="[bold yellow]Incidents by Category[/bold yellow]", box=box.SIMPLE)
            cat_table.add_column("Category", style="cyan")
            cat_table.add_column("Count", style="white")
            for c, cnt in cats.items():
                cat_table.add_row(c, str(cnt))
            console.print(cat_table)

        recent = summary.get("recent_incidents", [])
        if recent:
            console.print("\n[bold yellow]Recent Auto-Remediations:[/bold yellow]")
            for inc in recent[-5:]:
                st = "[green]SUCCESS[/green]" if inc.get("success") else "[red]FAIL[/red]"
                console.print(f"  • [dim]{inc.get('timestamp')}[/dim] [{inc.get('category')}] ➔ {inc.get('action_taken')} ({st})")
        return

    if run_mcp_server:
        from .mcp_server import run_stdio_mcp_server
        asyncio.run(run_stdio_mcp_server())
        return

    if show_bandit_stats:
        from .resolver.core.bandit_router import GLOBAL_BANDIT_ROUTER
        telemetry = GLOBAL_BANDIT_ROUTER.get_telemetry()
        if json_output:
            print(json.dumps(telemetry, indent=2))
            return
        b_table = Table(title="[bold bright_cyan]🎰 BAYESIAN THOMPSON SAMPLING MIRROR ROUTER (V4.0 OMEGA)[/bold bright_cyan]", box=box.ROUNDED, border_style="cyan")
        b_table.add_column("CDN / Hoster Arm", style="bold white")
        b_table.add_column("Tier Class", style="cyan")
        b_table.add_column("Posterior Beta(α, β)", justify="center", style="magenta")
        b_table.add_column("Mean Rel.", justify="right", style="bold green")
        b_table.add_column("EWMA Latency", justify="right", style="yellow")
        b_table.add_column("Expected Score", justify="right", style="bold bright_green")
        for arm in telemetry.get("arms", []):
            b_table.add_row(
                arm["arm_id"],
                arm["tier_label"],
                f"Beta({arm['alpha']:.1f}, {arm['beta']:.1f})",
                f"{arm['mean_reliability']*100:.1f}%",
                f"{arm['ewma_latency_ms']:.1f} ms",
                f"{arm['expected_score']:.4f}",
            )
        console.print(b_table)
        return

    if predict_hops_url:
        from .resolver.core.speculative_hop import GLOBAL_HOP_PREDICTOR
        res = asyncio.run(GLOBAL_HOP_PREDICTOR.speculative_prewarm(predict_hops_url))
        if json_output:
            print(json.dumps(res, indent=2))
            return
        p_table = Table(title=f"[bold bright_magenta]🔮 SPECULATIVE MARKOV HOP PREDICTION — {res.get('entry_domain')}[/bold bright_magenta]", box=box.ROUNDED)
        p_table.add_column("Step", justify="center", style="bold cyan")
        p_table.add_column("From Domain", style="yellow")
        p_table.add_column("Predicted Next Hop", style="bold bright_green")
        p_table.add_column("Confidence", justify="right", style="magenta")
        p_table.add_column("DoH Pre-Warmed IP", style="cyan")
        warmed_map = res.get("domains_prewarmed", {})
        for hop in res.get("predicted_chain", []):
            dst = hop["predicted_domain"]
            p_table.add_row(
                f"Hop {hop['step']}",
                hop["source_domain"],
                dst,
                f"{hop['probability']*100:.1f}%",
                str(warmed_map.get(dst) or "Cached / Ready"),
            )
        console.print(p_table)
        return

    if deobfuscate_input:
        from .resolver.core.ast_deobfuscator import deobfuscate_javascript_ast
        p_candidate = Path(deobfuscate_input)
        raw_js = p_candidate.read_text(encoding="utf-8", errors="replace") if p_candidate.is_file() else deobfuscate_input
        ast_res = deobfuscate_javascript_ast(raw_js)
        if json_output:
            print(json.dumps(ast_res.to_dict(), indent=2))
            return
        d_table = Table(title="[bold bright_cyan]🧬 7-PASS SYMBOLIC & AST JS DEOBFUSCATOR[/bold bright_cyan]", box=box.ROUNDED)
        d_table.add_column("Pass Name", style="cyan")
        d_table.add_column("Transforms Applied", justify="right", style="bold yellow")
        d_table.add_column("Time (ms)", justify="right", style="green")
        for pm in ast_res.passes:
            d_table.add_row(pm.pass_name, str(pm.transforms_applied), f"{pm.duration_ms:.4f} ms")
        console.print(d_table)
        console.print(f"\n[bold green]✔ Deobfuscated Source ({ast_res.total_duration_ms:.3f} ms):[/bold green]\n[white]{ast_res.deobfuscated_source}[/white]")
        if ast_res.extracted_urls:
            console.print("\n[bold bright_yellow]🔗 Extracted URLs / Streams:[/bold bright_yellow]")
            for u in ast_res.extracted_urls:
                console.print(f"  • [bold bright_green]{u}[/bold bright_green]")
        return

    if run_omega_bench:
        from .mcp_server import run_omega_benchmark
        bench = run_omega_benchmark(iterations=200)
        if json_output:
            print(json.dumps(bench, indent=2))
            return
        o_table = Table(title="[bold bright_cyan]⚡ RIPPER V4.0 OMEGA MULTI-ENGINE BENCHMARK SUITE (200 ITERS)[/bold bright_cyan]", box=box.ROUNDED, border_style="bright_magenta")
        o_table.add_column("Subsystem Engine", style="bold white")
        o_table.add_column("Per-Op Latency", justify="right", style="bold yellow")
        o_table.add_column("Throughput", justify="right", style="bold bright_green")
        o_table.add_column("Verification Sample", style="dim cyan")
        b_map = bench.get("benchmarks", {})
        for key, metrics in b_map.items():
            sample_str = str(
                metrics.get("sample_output")
                or (metrics.get("extracted_urls") or [""])[0]
                or (metrics.get("winner") or {}).get("arm_id")
                or "Verified OK"
            )[:48]
            o_table.add_row(
                key.replace("_", " ").title(),
                f"{metrics['per_op_us']:.2f} µs",
                f"{metrics['ops_per_sec']:,} ops/sec",
                sample_str,
            )
        console.print(o_table)
        return


    if ai_parse_query:
        from .ai_engine import parse_query_ai
        plan = parse_query_ai(ai_parse_query)
        console.print(f"[bold cyan]🧠 AI Query Plan for:[/bold cyan] {ai_parse_query}")
        console.print(f"  [bold]Cleaned Title:[/bold] {plan.cleaned_title}")
        console.print(f"  [bold]Media Type:[/bold] {plan.media_type}")
        console.print(f"  [bold]Year:[/bold] {plan.year}")
        console.print(f"  [bold]Season/Episode:[/bold] S{plan.season or 0:02d}E{plan.episode or 0:02d}" if plan.season else "  [bold]Season/Episode:[/bold] N/A")
        console.print(f"  [bold]Quality:[/bold] {plan.quality_target}")
        console.print(f"  [bold]Codec:[/bold] {plan.codec_preference or 'ANY'}")
        console.print(f"  [bold]Audio:[/bold] {plan.audio_preference or 'ANY'}")
        console.print(f"  [bold]Keywords:[/bold] {', '.join(plan.search_keywords)}")
        return

    if launch_chat or ai_copilot_prompt == "CHAT_MODE":
        from .ai_engine import launch_ai_chat
        launch_ai_chat()
        return

    if ai_copilot_prompt:
        from .ai_engine import answer_user_query, display_copilot_response
        resp = answer_user_query(ai_copilot_prompt)
        display_copilot_response(resp)
        return

    # Interactive OlaMovies Login Assistant
    if login_olamovies:
        from .session_capture import capture_olamovies_session_interactively
        asyncio.run(capture_olamovies_session_interactively())
        return

    # 1-Click Playback Resume
    if resume:
        from .player import get_playback_resume_state, launch_video_stream_in_player
        state = get_playback_resume_state()
        if not state or not state.get("stream_url"):
            console.print("[bold red]❌ No previous playback session found to resume.[/bold red]")
            return
        stream_url = state["stream_url"]
        title = state.get("title", "Media Stream")
        sub_path = state.get("subtitle_path")
        console.print(f"[bold bright_cyan]▶ Resuming Playback: {title}...[/bold bright_cyan]")
        console.print(f"[dim]{stream_url[:75]}...[/dim]")
        ok, msg = launch_video_stream_in_player(stream_url, subtitle_path=sub_path)
        if ok:
            console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
        else:
            console.print(f"[bold red]❌ {msg}[/bold red]")
        return

    # Autonomous Site Hunter CLI Flag
    if hunt_site:
        from .hunter.site_hunter import SiteHunter
        sh = SiteHunter()
        asyncio.run(sh.hunt_sites(max_sites=50))
        return

    # Autonomous Movie Hunter CLI Flag
    if hunt_movie_query:
        from .hunter.site_hunter import SiteHunter
        from .hunter.movie_hunter import MovieHunter
        sh = SiteHunter()
        mh = MovieHunter(sh)
        asyncio.run(mh.hunt_movie(hunt_movie_query, max_results=30, verify_links=True))
        return

    # Trailer lookup flag
    if show_trailer and search_query:
        from .trailer import find_trailer, open_trailer_in_browser
        t_info = asyncio.run(find_trailer(search_query, year_filter))
        console.print(f"[bold green]🎬 Opening Trailer for '{search_query}':[/bold green] [dim]{t_info.get('trailer_url')}[/dim]")
        open_trailer_in_browser(t_info.get("trailer_url", ""))
        return

    # 0. Simulation Mode
    if simulate:
        from .simulation import run_autonomous_100_simulation
        asyncio.run(run_autonomous_100_simulation(verbose=True))
        return

    # Dedicated Web Player Launcher
    if launch_web_player:
        from .proxy_engine import ensure_proxy_running, LOCAL_PROXY_PORT
        import webbrowser
        ensure_proxy_running()
        url = f"http://127.0.0.1:{LOCAL_PROXY_PORT}/player"
        console.print(f"\n[bold green]🎬 Cinema Web Player Server Active![/bold green]")
        console.print(f"[bold cyan]👉 {url}[/bold cyan]\n")
        webbrowser.open(url)
        console.print("[dim]Press Ctrl+C to stop player server...[/dim]")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

    # AnyStream Universal Stream Extractor CLI Flag
    if any_stream_url:
        from .anystream import handle_anystream_cli
        asyncio.run(handle_anystream_cli(any_stream_url.strip()))
        return

    # Click'n'Load Port 9666 Daemon CLI Flag
    if cnl:
        from .universal_bypasser import CNL2Listener
        def on_recv(links):
            console.print(f"\n[bold green]✔ Click'n'Load Received {len(links)} link(s):[/bold green]")
            for l in links:
                console.print(f"  [bright_green]➔[/bright_green] {l}")
        listener = CNL2Listener(on_links_received=on_recv)
        console.print("[bold green]⚡ Click'n'Load (Port 9666) Daemon active! Listening for browser payloads...[/bold green]")
        console.print("[dim]Press Ctrl+C to stop daemon...[/dim]")
        asyncio.run(listener.start())
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            asyncio.run(listener.stop())
            return

    # Universal Shortlink & Container Bypass CLI Flag
    if bypass_url_target:
        from .universal_bypasser import UniversalBypasserEngine
        engine = UniversalBypasserEngine()
        res = asyncio.run(engine.resolve(bypass_url_target))
        if json_output:
            print(json.dumps(res.to_dict(), indent=2))
            return
        if hasattr(res, "unlocked_urls") and res.unlocked_urls:
            console.print(f"\n[bold green]✔ Container Unrolled ({res.duration:.2f}s): {len(res.unlocked_urls)} links found[/bold green]")
            for u in res.unlocked_urls:
                console.print(f"  [green]➔[/green] {u}")
        elif res.success and res.resolved_url:
            console.print(f"\n[bold green]✔ Bypass Successful ({res.duration:.2f}s):[/bold green] [bold white]{res.resolved_url}[/bold white]")
            if res.intermediate_urls:
                console.print("[dim]Hops:[/dim] " + " ➔ ".join(res.intermediate_urls))
        else:
            console.print(f"\n[bold red]❌ Bypass Failed:[/bold red] {res.error or 'Failed to resolve'}")
        return

    # Live FMHY Deep Crawl & Scraping CLI Flag
    if crawl_fmhy:
        from ripper.ripperdb.fmhy_sync import FMHYRegistrySync
        syncer = FMHYRegistrySync()
        if not json_output:
            console.print("[bold cyan]🕷️ Deep-Crawling https://fmhy.net/video live & GitHub Markdown...[/bold cyan]")
        res = syncer.crawl_live_and_diff()
        if json_output:
            print(json.dumps(res, indent=2))
        else:
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
                    console.print(f"[dim]... and {len(new_provs) - 15} more new providers registered in RipperDB.[/dim]")

            console.print("\n[bold green]✔ All updated sites and mirrors synced to RipperDB & domain_registry.json with zero data lost![/bold green]\n")
        return

    # FMHY Video Registry Sync CLI Flag
    if sync_fmhy or force_sync:
        from ripper.ripperdb.fmhy_sync import FMHYRegistrySync
        syncer = FMHYRegistrySync()
        res = syncer.sync(force=force_sync)
        if json_output:
            print(json.dumps(res, indent=2))
        else:
            table = Table(title="[bold bright_cyan]🌍 FMHY PROVIDER REGISTRY SYNCHRONIZATION (736+ BASELINE)[/bold bright_cyan]", box=box.ROUNDED)
            table.add_column("Metric", style="bold cyan")
            table.add_column("Value", style="bold green")
            table.add_row("Status", str(res.get("status", "unknown")))
            table.add_row("Providers Total", str(res.get("providers_total", 0)))
            table.add_row("Mirrors Total", str(res.get("mirrors_total", 0)))
            table.add_row("Archetypes", ", ".join(f"{k}: {v}" for k, v in res.get("archetypes", {}).items()))
            console.print(table)
        return

    # RipperDB Statistics & Telemetry CLI Flag
    if ripperdb_stats:
        from ripper.ripperdb.cache import RipperDBCache
        cache = RipperDBCache()
        stats = cache.get_stats()
        if json_output:
            print(json.dumps(stats, indent=2))
        else:
            table = Table(title="[bold bright_magenta]📊 RIPPERDB DATABASE & CACHE TELEMETRY[/bold bright_magenta]", box=box.ROUNDED)
            table.add_column("Database Component", style="bold cyan")
            table.add_column("Count / Status", style="bold yellow")
            table.add_row("Registered Providers", str(stats.get("providers_count", 0)))
            table.add_row("Active Mirrors", str(stats.get("mirrors_count", 0)))
            table.add_row("Cached Media Entities", str(stats.get("media_entities_count", 0)))
            table.add_row("Cached Releases", str(stats.get("release_items_count", 0)))
            table.add_row("Cached Direct Streams", str(stats.get("cached_streams_count", 0)))
            table.add_row("Database Path", str(stats.get("db_path", "")))
            console.print(table)
        return

    # Global Federated Search across 736+ Providers CLI Flag
    if global_search_query:
        from ripper.ripperdb.harvesters import HarvesterDispatcher
        from ripper.ripperdb.bridge import (
            format_stream_summary,
            launch_stream_in_player_with_headers,
            download_stream,
        )

        if not (json_output or watch or download_flag):
            asyncio.run(
                handle_global_search_flow(
                    initial_query=global_search_query,
                    season=season,
                    episode=episode,
                    min_quality=min_quality,
                    timeout=timeout,
                )
            )
            return

        dispatcher = HarvesterDispatcher()
        results = asyncio.run(
            dispatcher.federated_search(
                query=global_search_query,
                season=season,
                episode=episode,
                min_quality=min_quality,
                timeout=timeout,
            )
        )

        if json_output:
            out_data = [
                {
                    "item_id": r.item_id,
                    "title": r.title,
                    "provider": r.provider,
                    "archetype": r.archetype,
                    "quality_tag": r.quality_tag,
                    "quality_score": r.quality_score,
                    "page_url": r.page_url,
                    "stream_url": r.stream_url,
                    "seeders": r.seeders,
                    "size_bytes": r.size_bytes,
                }
                for r in results
            ]
            print(json.dumps(out_data, indent=2))
            return

        if not results:
            console.print(f"[bold red]❌ No releases found for '{global_search_query}' across all FMHY providers.[/bold red]")
            return

        # Check for auto-watch (-w) or auto-download (-dl)
        if watch or download_flag:
            top_item = results[0]
            console.print(f"\n[bold cyan]⚡ Resolving stream for top match: '{top_item.title}'...[/bold cyan]")
            resolved = asyncio.run(dispatcher.resolve_stream_link(top_item, timeout=timeout))
            if not resolved:
                console.print(f"[bold red]❌ Failed to resolve stream for: {top_item.page_url}[/bold red]")
                return
            if watch:
                success, msg = launch_stream_in_player_with_headers(resolved, title=top_item.title)
                if success:
                    console.print(f"[bold bright_green]✔ {msg}[/bold bright_green]")
                else:
                    console.print(f"[bold red]❌ {msg}[/bold red]")
            elif download_flag:
                download_stream(resolved, title=top_item.title)
            return

    # 1. Search Mode
    if search_query:
        asyncio.run(
            handle_search_flow(
                initial_query=search_query,
                timeout=timeout,
                target_site=target_site,
                language_filter=language_filter,
                query_year=year_filter,
                quality_filter=quality_filter,
                hdr=hdr,
                atmos=atmos,
                remux=remux,
                use_metadata_apis=not no_apis,
                export_path=export_search_path,
            )
        )
        return

    # 2. 1-Click Watch Mode
    if watch and urls:
        asyncio.run(run_one_click_instant_watch(urls[0], timeout=timeout, audio_language=audio_language))
        return

    # 3. Media Grid Mode
    if media or paste_content:
        raw_html = paste_content or ""
        base_url = urls[0] if urls else "https://cinefreak.net"

        if not raw_html and urls:
            try:
                with httpx.Client(timeout=timeout + 3.0, verify=False) as client:
                    resp = client.get(urls[0], headers={"User-Agent": DEFAULT_USER_AGENT})
                    raw_html = resp.text
            except Exception as e:
                console.print(f"[bold red]❌ Failed to fetch webpage: {e}[/bold red]")
                sys.exit(1)

        if not raw_html:
            console.print("[bold red]❌ Error: No HTML content provided for media extraction.[/bold red]")
            sys.exit(1)

        media_items = extract_media_items_from_html(raw_html, base_url)
        console.print(f"\n[bold green]✔ Extracted {len(media_items)} Download Item(s) from scoped containers.[/bold green]")
        console.print("[bold cyan]⚡ Deep-resolving server mirrors to direct Cloudflare R2 / S3 streams...[/bold cyan]\n")
        resolved = asyncio.run(deep_resolve_media_items(media_items, max_hops=max_hops, timeout=timeout))
        render_media_grid_summary(resolved)

        # Interactive User Selection for Quality & Server Mirror Action
        if resolved:
            from rich.prompt import Prompt, Confirm
            from .interactive import handle_server_action_menu
            
            # Flatten available streams/qualities
            available_targets = []
            for item in resolved:
                title = f"{item.title} [{item.resolution}] [{item.size or ''}]"
                if item.servers:
                    for s in item.servers:
                        s_url = s.direct_download_url or s.intermediate_url
                        if s_url:
                            available_targets.append((f"{title} -> {s.label}", s_url, bool(s.direct_download_url), f"{item.title}_{item.resolution}.mkv"))
                elif item.unshortened_landing_url:
                    available_targets.append((f"{title} -> Direct Link", item.unshortened_landing_url, True, f"{item.title}_{item.resolution}.mkv"))

            if available_targets:
                console.print("\n[bold green]✔ Quality releases and server mirrors detected.[/bold green]")
                if Confirm.ask("Would you like to select a quality release to play or download now?", default=True):
                    table = Table(title="🎬 SELECT QUALITY & HOST RELEASE", box=box.ROUNDED)
                    table.add_column("#", justify="right", style="bold cyan", width=4)
                    table.add_column("Release & Host", style="bold yellow")
                    for idx, (label, _, _, _) in enumerate(available_targets, 1):
                        table.add_row(str(idx), label)
                    console.print(table)

                    choices = [str(i) for i in range(1, len(available_targets) + 1)] + ["0"]
                    sel = Prompt.ask("Choose release # to play/download (or '0' to exit)", choices=choices, default="1")
                    if sel != "0":
                        chosen_label, chosen_url, is_direct, chosen_fn = available_targets[int(sel) - 1]
                        asyncio.run(handle_server_action_menu(chosen_label, chosen_url, is_direct, chosen_fn))
        return

    # If no arguments provided, or explicit -i, launch interactive menu
    if (not urls and not file_path) or interactive:
        launch_interactive_unshortener()
        return

    # Gather targets
    target_urls: List[str] = list(urls)

    if file_path:
        file_urls = parse_urls_from_file_path(Path(file_path))
        target_urls.extend(file_urls)

    if not target_urls:
        console.print("[bold red]❌ Error: No valid URLs provided. Use -h for help.[/bold red]")
        sys.exit(1)

    # 4. Smart Auto-Detector & Intent Router (Phase 1 & 4)
    if len(target_urls) == 1 and not output_path and not json_output:
        raw_target = target_urls[0]
        from .autodetect import classify_user_input, InputIntent

        plan = classify_user_input(raw_target)

        # AI Assistant / Conversational Question or Command
        if plan.intent == InputIntent.AI_ASSISTANT:
            from .ai_engine import display_copilot_response, answer_user_query
            resp = plan.ai_plan if (plan.ai_plan and hasattr(plan.ai_plan, "answer")) else answer_user_query(raw_target)
            display_copilot_response(resp)
            return

        # A. If it's a Movie or Series Search Query -> Route directly to search engine flow
        if plan.intent in (InputIntent.SEARCH_MOVIE, InputIntent.SEARCH_TV_SERIES):
            query = plan.query_specs.clean_title if plan.query_specs else raw_target
            year_str = str(plan.query_specs.year) if (plan.query_specs and plan.query_specs.year) else year_filter
            q_pref = (plan.query_specs.quality_pref if plan.query_specs and plan.query_specs.quality_pref else quality_filter)
            lang_pref = (plan.query_specs.audio_pref if plan.query_specs and plan.query_specs.audio_pref else language_filter)
            console.print(f"\n[bold cyan]🧠 Auto-Detector: Identified search query '[bold white]{query}[/bold white]'[/bold cyan]")
            asyncio.run(
                handle_search_flow(
                    initial_query=query,
                    timeout=timeout,
                    target_site=target_site,
                    language_filter=lang_pref,
                    query_year=year_str,
                    quality_filter=q_pref,
                    hdr=hdr,
                    atmos=atmos,
                    remux=remux,
                    use_metadata_apis=not no_apis,
                    export_path=export_search_path,
                )
            )
            return

        # B. If it's an HTML container snippet -> Route to media extraction
        if plan.intent == InputIntent.HTML_SNIPPET:
            media_items = extract_media_items_from_html(raw_target, "https://cinefreak.net")
            resolved = asyncio.run(deep_resolve_media_items(media_items, max_hops=max_hops, timeout=timeout))
            render_media_grid_summary(resolved)
            return

        # C. URL Mode (Normalized)
        url = plan.normalized_url or raw_target
        res = asyncio.run(unshorten_url(url, max_hops=max_hops, timeout=timeout, deep_crawl_servers=True))
        display_unshorten_summary(res)

        # Prompt interactive actions to play or download media
        from .interactive import prompt_play_or_download_flow
        asyncio.run(prompt_play_or_download_flow(res))

        if deep:
            console.print("\n[bold yellow]📋 DETAILED HTTP HEADERS PER HOP:[/bold yellow]")
            for h in res.hops:
                console.print(f"\n[bold cyan]Hop {h.hop_number} ({h.redirect_type}) -> {h.url}[/bold cyan]")
                if h.headers:
                    for k, v in h.headers.items():
                        console.print(f"  [dim]{k}:[/dim] [white]{v}[/white]")
        return

    # 5. Batch / JSON Mode
    results = asyncio.run(
        batch_unshorten_urls(
            target_urls,
            concurrency=concurrency,
            max_hops=max_hops,
            timeout=timeout,
            show_progress=(not json_output),
        )
    )

    if json_output:
        output_data = [r.to_dict() for r in results]
        print(json.dumps(output_data, indent=2))
        return

    display_batch_summary_table(results)

    if output_path:
        export_results_to_file(results, Path(output_path))
        console.print(f"\n[bold green]✔ Successfully exported {len(results)} results to: {output_path}[/bold green]")


if __name__ == "__main__":
    main()

