# 📺 TV SERIES BATCH & EPISODE TREE PARSER
### Multi-Season Matrix Parsing, Zip Pack Unpackers & Episode Selection Modal

---

## 1. The TV Series Page Structure Challenge

Movie sites structure TV series pages with complex nested hierarchies:
* **Multiple Seasons**: Season 1, Season 2, Season 3 tabs.
* **Multiple Quality Tiers per Episode**: 480p, 720p x265, 1080p 10bit, 4K HDR.
* **Batch Downloads vs Single Episodes**: "Zip Pack 720p (4.5GB)" vs "Episode 1 (450MB)", "Episode 2 (450MB)".

---

## 2. Tree Data Model (`unshorten/models.py`)

```python
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class EpisodeItem:
    episode_num: int
    title: str
    qualities: Dict[str, str] # e.g. {"1080p": "https://hubcloud...", "720p": "https://..."}

@dataclass
class SeasonItem:
    season_num: int
    episodes: List[EpisodeItem] = field(default_factory=list)
    zip_packs: Dict[str, str] = field(default_factory=dict) # e.g. {"Complete 720p Zip": "https://..."}

@dataclass
class TVSeriesTree:
    series_title: str
    total_seasons: int
    seasons: Dict[int, SeasonItem] = field(default_factory=dict)
```

---

## 3. Parsing Heuristics & RegEx Patterns

The parser scans the HTML DOM using structured regex patterns:
* Season regex: `(?i)(?:season|s)\s*(\d{1,2})`
* Episode regex: `(?i)(?:episode|ep|e)\s*(\d{1,3})`
* Quality regex: `(?i)(2160p|1080p|720p|480p|4K|HEVC|x265)`

The CLI and Web UI present this tree as an **Interactive Accordion Tree** where you can select:
* `Play Season 1 Episode 5 [1080p]` $\rightarrow$ starts streaming in PotPlayer immediately.
* `Download Season 2 Complete Zip [720p]` $\rightarrow$ queues batch download.
