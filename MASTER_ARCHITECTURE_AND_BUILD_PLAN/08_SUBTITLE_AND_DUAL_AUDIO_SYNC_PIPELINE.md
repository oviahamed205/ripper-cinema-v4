# 💬 SUBTITLE & DUAL-AUDIO SYNC PIPELINE
### SubDL, OpenSubtitles v3 & Release Hash Subtitle Auto-Matching

---

## 1. The Subtitle Sync Challenge
When streaming movies from various release groups (e.g. `YTS`, `PSA`, `GalaxyRG`, `Pahe`, `Vega`), audio tracks often feature Dual-Audio (Hindi + English) with no embedded subtitles.

Downloading generic subtitles often results in **audio-sync drift** (subtitles appearing 2.5 seconds early or late).

---

## 2. Release Title Hashing & Fuzzy Matcher (`unshorten/subtitles.py`)

The subtitle engine extracts the exact release token from the stream or post title:

```python
import re
import httpx

def extract_release_signature(post_title: str) -> dict:
    """Extracts resolution, codec, audio, and source tags for perfect subtitle matching."""
    return {
        "year": re.search(r"\b(19\d\d|20\d\d)\b", post_title).group(0) if re.search(r"\b(19\d\d|20\d\d)\b", post_title) else "",
        "quality": re.search(r"\b(2160p|1080p|720p|480p|4K|UHD)\b", post_title, re.I).group(0) if re.search(r"\b(2160p|1080p|720p|480p|4K|UHD)\b", post_title, re.I) else "",
        "source": re.search(r"\b(WEB-DL|WEBRip|BluRay|HDRip|DVDRip|NF|AMZN)\b", post_title, re.I).group(0) if re.search(r"\b(WEB-DL|WEBRip|BluRay|HDRip|DVDRip|NF|AMZN)\b", post_title, re.I) else "",
        "codec": re.search(r"\b(x264|x265|HEVC|H\.264|H\.265|10bit)\b", post_title, re.I).group(0) if re.search(r"\b(x264|x265|HEVC|H\.264|H\.265|10bit)\b", post_title, re.I) else "",
    }
```

---

## 3. SubDL & OpenSubtitles Waterfall

1. **SubDL REST API (`api.subdl.com/api/v1/subtitles`)**: Queries using clean movie title + IMDB ID + release signature.
2. **OpenSubtitles REST v3 (`api.opensubtitles.com/api/v1/subtitles`)**: Fallback query for multi-language subtitles.
3. **Auto-Download & Cache**: Saves `.srt` file directly to `~/.unshorten/subtitles/<movie_id>.srt` and passes it directly to PotPlayer or VLC via CLI arguments.
