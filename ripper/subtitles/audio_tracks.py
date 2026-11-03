"""
ripper.subtitles.audio_tracks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Multi-language audio track inspector & selector.
Probes live media streams or local files via ffprobe or metadata analysis,
detects available language audio channels (Hindi, English, Tamil, Telugu, Spanish, Japanese, etc.),
and provides interactive/programmatic selection for media players (MPV, VLC, PotPlayer).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("ripper.subtitles.audio_tracks")

LANGUAGE_MAP: Dict[str, Tuple[str, str]] = {
    "hin": ("Hindi", "hi"),
    "hindi": ("Hindi", "hi"),
    "eng": ("English", "en"),
    "english": ("English", "en"),
    "tam": ("Tamil", "ta"),
    "tamil": ("Tamil", "ta"),
    "tel": ("Telugu", "te"),
    "telugu": ("Telugu", "te"),
    "mal": ("Malayalam", "ml"),
    "malayalam": ("Malayalam", "ml"),
    "kan": ("Kannada", "kn"),
    "kannada": ("Kannada", "kn"),
    "ben": ("Bengali", "bn"),
    "bengali": ("Bengali", "bn"),
    "mar": ("Marathi", "mr"),
    "marathi": ("Marathi", "mr"),
    "pun": ("Punjabi", "pa"),
    "punjabi": ("Punjabi", "pa"),
    "spa": ("Spanish", "es"),
    "spanish": ("Spanish", "es"),
    "fre": ("French", "fr"),
    "fra": ("French", "fr"),
    "french": ("French", "fr"),
    "ger": ("German", "de"),
    "deu": ("German", "de"),
    "german": ("German", "de"),
    "ita": ("Italian", "it"),
    "italian": ("Italian", "it"),
    "jpn": ("Japanese", "ja"),
    "japanese": ("Japanese", "ja"),
    "kor": ("Korean", "ko"),
    "korean": ("Korean", "ko"),
    "chi": ("Chinese", "zh"),
    "zho": ("Chinese", "zh"),
    "chinese": ("Chinese", "zh"),
    "rus": ("Russian", "ru"),
    "russian": ("Russian", "ru"),
    "ara": ("Arabic", "ar"),
    "arabic": ("Arabic", "ar"),
}


@dataclass
class AudioTrackInfo:
    index: int
    language_code: str
    display_name: str
    codec: str = ""
    channels: int = 2
    title: str = ""
    is_default: bool = False


def parse_audio_languages_from_title(title_or_codec: str) -> List[AudioTrackInfo]:
    """
    Infers likely audio tracks from movie release titles like:
    'Dual Audio [Hindi + English]' or '[Hindi-Eng-Tam-Tel]'.
    """
    clean = title_or_codec.lower()
    tracks: List[AudioTrackInfo] = []
    seen_codes = set()

    # Match tokens like hindi, english, dual audio, multi audio
    idx = 0
    for key, (display, iso_code) in LANGUAGE_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", clean):
            if iso_code not in seen_codes:
                seen_codes.add(iso_code)
                tracks.append(
                    AudioTrackInfo(
                        index=idx,
                        language_code=iso_code,
                        display_name=display,
                        is_default=(idx == 0),
                    )
                )
                idx += 1

    if not tracks:
        if "dual audio" in clean:
            tracks.append(AudioTrackInfo(index=0, language_code="hi", display_name="Hindi", is_default=True))
            tracks.append(AudioTrackInfo(index=1, language_code="en", display_name="English", is_default=False))
        elif "multi audio" in clean:
            tracks.append(AudioTrackInfo(index=0, language_code="hi", display_name="Hindi", is_default=True))
            tracks.append(AudioTrackInfo(index=1, language_code="en", display_name="English", is_default=False))
            tracks.append(AudioTrackInfo(index=2, language_code="ta", display_name="Tamil", is_default=False))
            tracks.append(AudioTrackInfo(index=3, language_code="te", display_name="Telugu", is_default=False))

    return tracks


def probe_remote_stream_audio_tracks(url: str, timeout: float = 6.0) -> List[AudioTrackInfo]:
    """
    Runs ffprobe non-destructively against the media stream URL to extract actual embedded audio tracks.
    """
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return []

    cmd = [
        ffprobe_bin,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        url,
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if proc.returncode == 0 and proc.stdout:
            data = json.loads(proc.stdout)
            streams = data.get("streams", [])
            tracks: List[AudioTrackInfo] = []
            for s in streams:
                idx = s.get("index", len(tracks))
                codec = s.get("codec_name", "").upper()
                channels = s.get("channels", 2)
                tags = s.get("tags", {})
                raw_lang = tags.get("language", "und").lower()
                disposition = s.get("disposition", {})
                is_def = bool(disposition.get("default", 0))

                display, iso = LANGUAGE_MAP.get(raw_lang, (raw_lang.upper(), raw_lang))
                title = tags.get("title", "")

                tracks.append(
                    AudioTrackInfo(
                        index=idx,
                        language_code=iso,
                        display_name=display,
                        codec=codec,
                        channels=channels,
                        title=title,
                        is_default=is_def,
                    )
                )
            return tracks
    except Exception as e:
        logger.debug(f"[AudioTracks] ffprobe probe failed: {e}")

    return []
