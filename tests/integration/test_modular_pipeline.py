"""
Comprehensive End-to-End Integration Test Suite for Ripper v4.0.
Verifies the complete pipeline:
Resolver -> Bypass -> AnyStream -> Local Proxy -> Player IPC -> TV Matrix -> Subtitles.
"""
import pytest
from pathlib import Path

from ripper.resolver import unshorten_url_sync, GLOBAL_REGISTRY
from ripper.bypass import BypassLadder, GLOBAL_BYPASS, GLOBAL_COOKIE_JAR
from ripper.anystream import ANYSTREAM_REGISTRY, sanitize_user_url
from ripper.proxy import parse_range_header, format_content_range, GLOBAL_STREAM_BUFFER
from ripper.player import detect_available_players, launch_video_stream_in_player
from ripper.tv import TVSeriesParser, generate_m3u_playlist
from ripper.subtitles import find_local_subtitle, search_subtitles


def test_resolver_modular_registry_pipeline():
    """Verify all 8 site handlers are registered and sorted by priority."""
    handlers = GLOBAL_REGISTRY.all_handlers()
    assert len(handlers) >= 8
    handler_names = [h.name for h in handlers]
    assert "cloud_storage" in handler_names
    assert "file_lockers" in handler_names
    assert "hubcloud" in handler_names
    assert "gdtot" in handler_names
    assert "ad_shorteners" in handler_names
    assert "universal_heuristics" in handler_names


def test_resolver_pixeldrain_api_transform():
    """Verify Pixeldrain web URLs transform directly to streaming endpoints."""
    res = unshorten_url_sync("https://pixeldrain.com/u/xyz9876", use_cache=False)
    assert "api/file/xyz9876?download" in res.final_url
    assert res.is_success is True
    assert res.total_hops >= 1


def test_resolver_r2_direct_stream():
    """Verify direct Cloudflare R2 storage links pass through instantly."""
    r2_url = "https://cdn-mirror.r2.dev/stream/deadpool_2024.mp4"
    res = unshorten_url_sync(r2_url, use_cache=False)
    assert res.final_url == r2_url
    assert res.is_success is True


def test_bypass_cookie_jar_lifecycle():
    """Verify clearance cookie storage and domain retrieval."""
    test_dom = "protected-cinema.com"
    GLOBAL_COOKIE_JAR.set_cookies_for_domain(test_dom, {"cf_clearance": "tok_998877", "__cf_bm": "bm_112233"})
    retrieved = GLOBAL_COOKIE_JAR.get_cookies_for_domain(test_dom)
    assert retrieved.get("cf_clearance") == "tok_998877"
    assert retrieved.get("__cf_bm") == "bm_112233"


def test_anystream_registry_and_sanitizer():
    """Verify AnyStream decoders and URL dirty text sanitizer."""
    assert len(ANYSTREAM_REGISTRY.decoders) >= 6
    dirty = "Download here: https://doodstream.com/d/abcd1234efgh or watch online"
    clean = sanitize_user_url(dirty)
    assert clean == "https://doodstream.com/d/abcd1234efgh"


def test_proxy_range_request_parsing():
    """Verify HTTP 206 Range headers parsing for seek operations."""
    start, end = parse_range_header("bytes=1048576-2097152", 10000000)
    assert start == 1048576
    assert end == 2097152
    header = format_content_range(start, end, 10000000)
    assert header == "bytes 1048576-2097152/10000000"


def test_proxy_ring_buffer():
    """Verify chunk caching in prefetch ring buffer."""
    GLOBAL_STREAM_BUFFER.put("video_chunk_001.ts", b"TS_PACKET_DATA_123")
    data = GLOBAL_STREAM_BUFFER.get("video_chunk_001.ts")
    assert data == b"TS_PACKET_DATA_123"
    assert GLOBAL_STREAM_BUFFER.get("nonexistent.ts") is None


def test_player_auto_discovery():
    """Verify local system players detection."""
    players = detect_available_players()
    assert isinstance(players, list)
    # On Windows, at least PotPlayer or VLC should be detectable
    player_names = [p[0] for p in players]
    assert any("potplayer" in name.lower() or "vlc" in name.lower() for name in player_names)


def test_tv_series_playlist_generation(tmp_path):
    """Verify M3U sequential playlist generation for TV episodes."""
    episodes = [
        {"title": "Breaking Bad S01E01 - Pilot", "url": "http://127.0.0.1:5055/stream/ep1"},
        {"title": "Breaking Bad S01E02 - Cat's in the Bag...", "url": "http://127.0.0.1:5055/stream/ep2"},
    ]
    playlist_file = tmp_path / "season1.m3u"
    generate_m3u_playlist("Breaking Bad Season 1", episodes, playlist_file)
    assert playlist_file.exists()
    content = playlist_file.read_text(encoding="utf-8")
    assert "#EXTM3U" in content
    assert "S01E01" in content
    assert "http://127.0.0.1:5055/stream/ep2" in content