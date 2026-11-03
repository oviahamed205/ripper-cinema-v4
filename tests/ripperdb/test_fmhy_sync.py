"""
Tests for ripper.ripperdb.fmhy_sync
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Covers:
- Markdown parsing of FMHY directory structure
- Extraction of primary sites and multi-mirrors
- Archetype identification (pstream, dooplay, embed, torrent, ddl)
- Database synchronization
- Atomic updating of hoster_watchdog/domain_registry.json
"""

import json
from pathlib import Path
import pytest
from ripper.ripperdb.cache import RipperDBCache
from ripper.ripperdb.fmhy_sync import (
    FMHYRegistrySync,
    clean_domain,
    detect_archetype,
)

SAMPLE_FMHY_MARKDOWN = """
# 🎬 FMHY Master Video & Movie Sites Directory

## 📂 Streaming Sites

### 🔹 Stream Aggregators
- **[Cinejoy](https://cinejoy.to/)** \\- Movies / TV / Anime / Auto-Next /
- **[Rive](https://www.rivestream.app/)**, [2](https://rivestream.ru/), [3](https://rivestream.vip/) or [CorsFlix](https://watch.corsflix.net/) \\- Movies / TV / Anime / Auto-Next / 4K / [Status](https://rentry.co/rivestream) /
- **[Flixer](https://flixer.gd/)**, [2](https://flixer.su/) or [Hexa](https://hexa.su/) \\- Movies / TV / Anime / Auto-Next

### 🔹 P-Stream Forks
- **[Z-Stream](https://zstream.mov/)** \\- Movies / TV / Anime / Auto-Next / 4K / [Status](https://rentry.co/xpstream)
- **[Aether](https://aether.ist/)**, [2](https://aether.cx/) \\- Movies / TV / Anime / Auto-Next / 4K

## 📂 DDL (Direct Download) Sites
- **[VegaMovies](https://vegamovies.im/)**, [2](https://vegamovies.yt/) \\- Fast DDL / 4K / Multi-Audio

## 📂 Torrent Sites
- **[1337x](https://1337x.to/)**, [2](https://1337x.so/) \\- Torrents / Movies / TV
"""


def test_clean_domain():
    assert clean_domain("https://www.rivestream.app/watch") == "rivestream.app"
    assert clean_domain("http://cinejoy.to:8080/path") == "cinejoy.to"
    assert clean_domain("invalid-url") == "invalid-url"


def test_detect_archetype():
    assert detect_archetype("Z-Stream", "https://zstream.mov", "p-stream fork") == "pstream"
    assert detect_archetype("1337x", "https://1337x.to", "torrent site") == "torrent"
    assert detect_archetype("VegaMovies", "https://vegamovies.im", "ddl download") == "ddl"
    assert detect_archetype("Cinejoy", "https://cinejoy.to", "movies stream") == "embed"


def test_parse_markdown():
    syncer = FMHYRegistrySync()
    providers = syncer.parse_markdown(SAMPLE_FMHY_MARKDOWN)

    assert len(providers) >= 6

    # Test Cinejoy
    cinejoy = next(p for p in providers if p.name == "Cinejoy")
    assert cinejoy.primary_url == "https://cinejoy.to/"
    assert cinejoy.supports_auto_next is True
    assert cinejoy.section == "streaming"

    # Test Rive multi-mirrors and status page
    rive = next(p for p in providers if p.name == "Rive")
    assert rive.primary_url == "https://www.rivestream.app/"
    assert len(rive.mirrors) == 4  # primary + ru + vip + corsflix
    assert rive.supports_4k is True
    assert rive.status_page == "https://rentry.co/rivestream"

    # Test P-Stream archetype
    zstream = next(p for p in providers if p.name == "Z-Stream")
    assert zstream.archetype == "pstream"

    # Test DDL section
    vegamovies = next(p for p in providers if p.name == "VegaMovies")
    assert vegamovies.section == "ddl"
    assert len(vegamovies.mirrors) == 2


def test_sync_to_db_and_watchdog(tmp_path):
    db_file = tmp_path / "sync_test.sqlite"
    cache = RipperDBCache(db_file)
    syncer = FMHYRegistrySync(cache_engine=cache)

    registry_json_mock = tmp_path / "domain_registry.json"
    syncer.registry_path = registry_json_mock

    providers = syncer.parse_markdown(SAMPLE_FMHY_MARKDOWN)
    synced_count = syncer.sync_to_db(providers)
    assert synced_count == len(providers)

    # Verify DB has providers
    db_provs = cache.list_providers()
    assert len(db_provs) == len(providers)

    # Verify watchdog JSON update
    syncer.update_watchdog_registry(providers)
    assert registry_json_mock.exists()

    with open(registry_json_mock, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "providers" in data
    assert "cinejoy" in data["providers"]
    assert "rivestream" in data["providers"]
    assert len(data["providers"]["rivestream"]["mirrors"]) >= 3

    cache.close()


def test_bundled_seed_loading_and_parsing():
    syncer = FMHYRegistrySync()
    seed_text = syncer.get_seed_markdown()
    assert len(seed_text) > 10000, "Bundled seed markdown should be populated"

    providers = syncer.parse_markdown(seed_text)
    assert len(providers) >= 50, f"Expected at least 50 providers from seed, got {len(providers)}"

    # Strict compliance: Zero Live TV, Sports, or IPTV sites
    for p in providers:
        lowered_sec = p.section.lower()
        assert "live tv" not in lowered_sec
        assert "sports" not in lowered_sec
        assert "iptv" not in lowered_sec

    # Verify key archetype detection on real directory entries
    names = [p.name for p in providers]
    assert any("Cinejoy" in n for n in names)
    assert any("Rive" in n for n in names)
    assert any("VegaMovies" in n for n in names)


def test_sync_all_pipeline(tmp_path, monkeypatch):
    db_file = tmp_path / "sync_all_test.sqlite"
    cache = RipperDBCache(db_file)
    syncer = FMHYRegistrySync(cache_engine=cache)

    registry_mock = tmp_path / "domain_registry.json"
    syncer.registry_path = registry_mock

    # Simulate offline by having fetch_live_markdown return None
    monkeypatch.setattr(syncer, "fetch_live_markdown", lambda: None)

    summary = syncer.sync_all(force_live=False, update_watchdog=True)

    assert summary["success"] is True
    assert summary["source"] == "bundled_seed"
    assert summary["providers_synced"] >= 50
    assert summary["total_mirrors"] >= summary["providers_synced"]
    assert "streaming" in summary["sections"]
    assert registry_mock.exists()

    # Verify SQLite DB has all synced records
    db_providers = cache.list_providers()
    assert len(db_providers) == summary["providers_synced"]

    cache.close()


SAMPLE_FMHY_HTML = """
<html>
<body>
  <h2>Streaming Sites</h2>
  <h3>Stream Aggregators</h3>
  <ul>
    <li><a href="https://cinejoy.to/">Cinejoy</a> - Movies / TV / Anime / Auto-Next /</li>
    <li><a href="https://www.rivestream.app/">Rive</a>, <a href="https://rivestream.ru/">2</a>, <a href="https://rivestream.vip/">3</a> or <a href="https://watch.corsflix.net">CorsFlix</a> - Movies / TV / Anime / Auto-Next / 4K / <a href="https://rentry.co/rivestream">Status</a></li>
  </ul>
  <h2>Download Sites</h2>
  <ul>
    <li><a href="https://vegamovies.im/">VegaMovies</a>, <a href="https://vegamovies.yt/">2</a> - Fast DDL / 4K</li>
  </ul>
  <h2>Live TV / Sports</h2>
  <ul>
    <li><a href="https://bad-sports.com/">BadSports</a> - Live Football</li>
  </ul>
</body>
</html>
"""


def test_parse_html():
    syncer = FMHYRegistrySync()
    providers = syncer.parse_html(SAMPLE_FMHY_HTML)

    assert len(providers) == 3
    cinejoy = next(p for p in providers if p.name == "Cinejoy")
    assert cinejoy.primary_url == "https://cinejoy.to/"
    assert cinejoy.supports_auto_next is True

    rive = next(p for p in providers if p.name == "Rive")
    assert len(rive.mirrors) == 4
    assert rive.supports_4k is True
    assert rive.status_page == "https://rentry.co/rivestream"

    # Verify Live TV / Sports was excluded
    names = [p.name for p in providers]
    assert "BadSports" not in names


def test_crawl_live_and_diff(tmp_path, monkeypatch):
    db_file = tmp_path / "diff_test.sqlite"
    cache = RipperDBCache(db_file)
    syncer = FMHYRegistrySync(cache_engine=cache)

    registry_mock = tmp_path / "domain_registry.json"
    syncer.registry_path = registry_mock

    # Mock fetch_live_html and fetch_live_markdown with sample data
    monkeypatch.setattr(syncer, "fetch_live_html", lambda: SAMPLE_FMHY_HTML)
    monkeypatch.setattr(syncer, "fetch_live_markdown", lambda: SAMPLE_FMHY_MARKDOWN)

    # 1st run: all items are new
    res1 = syncer.crawl_live_and_diff(update_watchdog=True)
    assert res1["success"] is True
    assert res1["status"] == "success"
    assert "live_html (fmhy.net/video)" in res1["sources_crawled"]
    assert "live_markdown (github/FMHYEdit)" in res1["sources_crawled"]
    assert res1["providers_total"] >= 6
    assert res1["new_providers_count"] == res1["providers_total"]
    assert res1["new_mirrors_count"] == res1["mirrors_total"]

    # 2nd run: 0 new items
    res2 = syncer.crawl_live_and_diff(update_watchdog=True)
    assert res2["success"] is True
    assert res2["new_providers_count"] == 0
    assert res2["new_mirrors_count"] == 0

    cache.close()


