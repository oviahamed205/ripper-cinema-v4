"""
Batch and parallel URL unshortening with file export capabilities.
"""

import re
import csv
import json
import asyncio
from pathlib import Path
from typing import List, Optional, Any

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from .models import UnshortenResult
from .resolver import unshorten_url
from .http_client import get_shared_client
from .ui import console


def extract_urls_from_raw_text(text: str) -> List[str]:
    """Extract all valid HTTP/HTTPS URLs from raw text, HTML, or markdown."""
    pattern = re.compile(r'https?://[^\s<>"\'\)\]\}]+', re.IGNORECASE)
    matches = pattern.findall(text)
    
    seen = set()
    unique = []
    for m in matches:
        clean = m.rstrip(".,;)]}>\"'\\/[")
        if clean.lower() not in seen:
            seen.add(clean.lower())
            unique.append(clean)
    return unique


def parse_urls_from_file_path(file_path: Path) -> List[str]:
    """Read URLs from a text, markdown, or CSV file."""
    if not file_path.exists():
        return []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return extract_urls_from_raw_text(content)
    except Exception:
        return []


async def batch_unshorten_urls(
    urls: List[str],
    concurrency: int = 10,
    max_hops: int = 15,
    timeout: float = 12.0,
    show_progress: bool = True,
) -> List[UnshortenResult]:
    """
    Unshorten multiple URLs in parallel with shared connection pool and concurrency limiting.
    """
    semaphore = asyncio.Semaphore(concurrency)
    client = await get_shared_client()
    results: List[UnshortenResult] = []

    async def _worker(url: str, progress, task_id):
        async with semaphore:
            res = await unshorten_url(url, max_hops=max_hops, timeout=timeout, client=client)
            if progress:
                progress.advance(task_id, 1)
            return res

    if show_progress:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(f"Unshortening {len(urls)} URLs...", total=len(urls))
            tasks = [_worker(u, progress, task_id) for u in urls]
            results = await asyncio.gather(*tasks)
    else:
        tasks = [_worker(u, None, None) for u in urls]
        results = await asyncio.gather(*tasks)

    return results


def export_results_to_file(results: List[UnshortenResult], export_path: Path):
    """Export unshortened results to JSON, CSV, or Markdown based on file extension."""
    export_path.parent.mkdir(parents=True, exist_ok=True)
    ext = export_path.suffix.lower()

    if ext == ".json":
        data = [r.to_dict() for r in results]
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    elif ext == ".csv":
        with open(export_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "Original URL", "Final URL", "Total Hops", "Total Time (ms)", "Risk Level", "Risk Score", "MIME Type"])
            for idx, r in enumerate(results, 1):
                writer.writerow([
                    idx,
                    r.original_url,
                    r.final_url,
                    r.total_hops,
                    round(r.total_time_ms, 2),
                    r.safety.risk_level,
                    r.safety.risk_score,
                    r.safety.mime_category,
                ])
    else:
        lines = ["# Unshorten Results Summary\n\n| # | Original Short Link | Final Destination URL | Hops | Risk | Time |\n| :--- | :--- | :--- | :---: | :---: | :---: |"]
        for idx, r in enumerate(results, 1):
            lines.append(f"| {idx} | `{r.original_url}` | `{r.final_url}` | {r.total_hops} | {r.safety.risk_level} | {round(r.total_time_ms, 1)}ms |")
        with open(export_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def export_search_results(results: List[Any], export_path: Path):
    """Export search results to JSON, CSV, or Markdown."""
    export_path.parent.mkdir(parents=True, exist_ok=True)
    ext = export_path.suffix.lower()

    if ext == ".json":
        data = []
        for r in results:
            data.append({
                "site": getattr(r, "site_name", ""),
                "title": getattr(r, "title", ""),
                "url": getattr(r, "url", ""),
                "year": getattr(r, "year", None),
                "quality_tags": getattr(r, "quality_tags", None),
                "season": getattr(r, "season", None),
                "episode": getattr(r, "episode", None),
                "language": getattr(r, "language", None),
            })
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    elif ext == ".csv":
        with open(export_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "Site", "Title", "Year", "Quality", "Language", "Season", "Episode", "URL"])
            for idx, r in enumerate(results, 1):
                writer.writerow([
                    idx,
                    getattr(r, "site_name", ""),
                    getattr(r, "title", ""),
                    getattr(r, "year", "") or "",
                    getattr(r, "quality_tags", "") or "",
                    getattr(r, "language", "") or "",
                    getattr(r, "season", "") or "",
                    getattr(r, "episode", "") or "",
                    getattr(r, "url", ""),
                ])
    else:
        lines = ["# Search Results\n\n| # | Site | Title | Year | Quality | Language | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
        for idx, r in enumerate(results, 1):
            year = f"({r.year})" if getattr(r, "year", None) else ""
            lang = getattr(r, "language", "") or "-"
            lines.append(f"| {idx} | {getattr(r, 'site_name', '')} | {getattr(r, 'title', '')} {year} | {getattr(r, 'quality_tags', '') or '-'} | {lang} | `{getattr(r, 'url', '')}` |")
        with open(export_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
