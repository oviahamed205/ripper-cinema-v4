"""
Precision Release Tag & Audio/Video Classifier for unshorten-cli.
Dissects release titles, file names, and descriptions to detect exact
technical audio, video, dynamic range, and print quality specifications.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ReleaseSpecs:
    title_raw: str
    resolution: str = "Unknown"  # 4K, 2160p, 1080p, 720p, 480p
    source_tier: str = "Unknown"  # REMUX, BluRay, WEB-DL, WEBRip, HDTV, CAM
    video_codec: str = "Unknown"  # AV1, HEVC/x265, AVC/x264
    dynamic_range: str = "SDR"  # Dolby Vision, HDR10+, HDR10, SDR
    audio_codec: str = "Unknown"  # Dolby Atmos, TrueHD, DDP 5.1, DTS-HD, AAC
    is_imax: bool = False
    is_dual_audio: bool = False
    is_multi_audio: bool = False
    languages: List[str] = field(default_factory=list)
    quality_score: float = 0.0


def classify_release(text: str) -> ReleaseSpecs:
    """Analyze a title/filename string and extract full technical specifications."""
    t = text or ""
    t_lower = t.lower()
    specs = ReleaseSpecs(title_raw=t)

    # 1. Resolution
    if any(k in t_lower for k in ("4k", "2160p", "uhd")):
        specs.resolution = "4K 2160p"
    elif any(k in t_lower for k in ("1080p", "fhd", "1080i")):
        specs.resolution = "1080p"
    elif "720p" in t_lower:
        specs.resolution = "720p"
    elif any(k in t_lower for k in ("480p", "dvd", "sd")):
        specs.resolution = "480p"

    # 2. Source Tier
    if "remux" in t_lower:
        specs.source_tier = "REMUX"
    elif any(k in t_lower for k in ("bluray", "blu-ray", "bdrip", "brrip")):
        specs.source_tier = "BluRay"
    elif any(k in t_lower for k in ("web-dl", "webdl")):
        specs.source_tier = "WEB-DL"
    elif any(k in t_lower for k in ("webrip", "web-rip")):
        specs.source_tier = "WEBRip"
    elif any(k in t_lower for k in ("hdtv", "tvrip", "pdtv")):
        specs.source_tier = "HDTV"
    elif any(k in t_lower for k in ("cam", "hdcam", "ts", "telesync", "tc", "hdts")):
        specs.source_tier = "CAM / Telesync"

    # 3. Dynamic Range & HDR
    has_dv = bool(re.search(r'\b(dv|dovi|dolby[\s\._-]*vision)\b', t_lower))
    has_hdr10plus = bool(re.search(r'\b(hdr10\+|hdr10plus)\b', t_lower))
    has_hdr10 = bool(re.search(r'\b(hdr10|hdr)\b', t_lower))

    if has_dv and (has_hdr10plus or has_hdr10):
        specs.dynamic_range = "Dolby Vision + HDR10"
    elif has_dv:
        specs.dynamic_range = "Dolby Vision"
    elif has_hdr10plus:
        specs.dynamic_range = "HDR10+"
    elif has_hdr10:
        specs.dynamic_range = "HDR10"

    # 4. Audio Codec
    if "atmos" in t_lower:
        specs.audio_codec = "Dolby Atmos"
    elif any(k in t_lower for k in ("truehd", "true-hd")):
        specs.audio_codec = "Dolby TrueHD"
    elif any(k in t_lower for k in ("dts-hd", "dtshd", "dts-x", "dts:x")):
        specs.audio_codec = "DTS-HD MA"
    elif any(k in t_lower for k in ("ddp5.1", "ddp 5.1", "dd+ 5.1", "eac3", "dd+")):
        specs.audio_codec = "Dolby Digital Plus 5.1"
    elif any(k in t_lower for k in ("dd5.1", "dd 5.1", "ac3")):
        specs.audio_codec = "Dolby Digital 5.1"
    elif "aac" in t_lower:
        specs.audio_codec = "AAC Stereo"

    # 5. IMAX
    if "imax" in t_lower:
        specs.is_imax = True

    # 6. Video Codec
    if any(k in t_lower for k in ("av1",)):
        specs.video_codec = "AV1"
    elif any(k in t_lower for k in ("x265", "h265", "hevc", "10bit", "10-bit")):
        specs.video_codec = "HEVC / 10-bit"
    elif any(k in t_lower for k in ("x264", "h264", "avc")):
        specs.video_codec = "H.264 / AVC"

    # 7. Audio Languages
    if "dual" in t_lower:
        specs.is_dual_audio = True
    if "multi" in t_lower:
        specs.is_multi_audio = True

    for lang in ("hindi", "english", "tamil", "telugu", "malayalam", "kannada", "bengali", "spanish", "french", "german", "japanese", "korean"):
        if lang in t_lower:
            specs.languages.append(lang.capitalize())

    # Calculate overall quality score (0 to 100)
    score = 50.0
    if specs.resolution == "4K 2160p":
        score += 25.0
    elif specs.resolution == "1080p":
        score += 15.0
    elif specs.resolution == "720p":
        score += 5.0
    elif specs.resolution == "480p":
        score -= 20.0

    if specs.source_tier == "REMUX":
        score += 20.0
    elif specs.source_tier == "BluRay":
        score += 15.0
    elif specs.source_tier == "WEB-DL":
        score += 10.0
    elif specs.source_tier == "CAM / Telesync":
        score -= 40.0

    if "Dolby Vision" in specs.dynamic_range:
        score += 10.0
    elif "HDR" in specs.dynamic_range:
        score += 7.0

    if specs.audio_codec in ("Dolby Atmos", "Dolby TrueHD", "DTS-HD MA"):
        score += 8.0
    elif specs.audio_codec == "Dolby Digital Plus 5.1":
        score += 5.0

    if specs.is_imax:
        score += 5.0

    specs.quality_score = max(0.0, min(100.0, score))
    return specs


def format_specs_badge(specs: ReleaseSpecs) -> str:
    """Generate compact Rich terminal badges for display in search tables."""
    badges = []
    if specs.resolution != "Unknown":
        res_color = "bold bright_magenta" if "4K" in specs.resolution else "bold yellow"
        badges.append(f"[{res_color}]{specs.resolution}[/{res_color}]")
    if specs.source_tier != "Unknown" and specs.source_tier != "CAM / Telesync":
        badges.append(f"[bold green]{specs.source_tier}[/bold green]")
    if specs.dynamic_range != "SDR":
        badges.append(f"[bold cyan]{specs.dynamic_range}[/bold cyan]")
    if specs.is_imax:
        badges.append("[bold bright_yellow]IMAX[/bold bright_yellow]")
    if specs.audio_codec != "Unknown":
        badges.append(f"[dim]{specs.audio_codec}[/dim]")
    return " | ".join(badges) if badges else "[dim]Standard[/dim]"
