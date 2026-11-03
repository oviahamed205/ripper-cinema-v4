"""
tests.ripperdb.test_cli_and_global_search
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit and integration tests for Phase 3:
- CLI flags: --sync-fmhy, --force-sync, --ripperdb-stats, -gs / --global-search
- Instant watch (-w) and instant download (-dl) CLI handoffs
- Bridge execution: player launcher with HTTP headers and subtitles, chunk downloader
- Interactive Cockpit Global Search flow and 4-level cascade triggering
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from ripper.cli import main
from ripper.ripperdb.bridge import (
    download_stream,
    format_stream_summary,
    launch_stream_in_player_with_headers,
)
from ripper.ripperdb.cache import CachedStream, ReleaseItem, RipperDBCache


@pytest.fixture
def mock_release_item():
    return ReleaseItem(
        provider_id="yts",
        raw_title="Inception (2010) [1080p] [BluRay] [5.1]",
        item_url="https://yts.mx/movies/inception-2010",
        clean_title="inception 2010",
        release_year=2010,
        resolution="1080p",
        codec="x264",
        quality_score=92.5,
        payload_json=json.dumps({
            "archetype": "torrent",
            "seeders": 150,
            "stream_url": "magnet:?xt=urn:btih:TESTHASH123&dn=Inception",
        }),
    )


@pytest.fixture
def mock_cached_stream():
    return CachedStream(
        id="stream_abc123",
        release_item_id="item_xyz987",
        direct_url="https://cdn.example.com/hls/master.m3u8",
        quality="1080p",
        expires_at="2030-01-01T00:00:00Z",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://streamprovider.com/",
            "X-Subtitles": json.dumps([{"url": "https://cdn.example.com/sub.vtt", "lang": "en"}]),
        },
        is_direct=True,
    )


def test_cli_ripperdb_stats():
    runner = CliRunner()
    result = runner.invoke(main, ["--ripperdb-stats"])
    assert result.exit_code == 0
    assert "RIPPERDB DATABASE & CACHE TELEMETRY" in result.output
    assert "Registered Providers" in result.output


def test_cli_ripperdb_stats_json():
    runner = CliRunner()
    result = runner.invoke(main, ["--ripperdb-stats", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "providers_count" in data
    assert "mirrors_count" in data
    assert "cached_streams_count" in data


def test_cli_sync_fmhy():
    runner = CliRunner()
    result = runner.invoke(main, ["--sync-fmhy"])
    assert result.exit_code == 0
    assert "FMHY PROVIDER REGISTRY SYNCHRONIZATION" in result.output
    assert "736" in result.output


def test_cli_sync_fmhy_json():
    runner = CliRunner()
    result = runner.invoke(main, ["--sync-fmhy", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data.get("status") == "success"
    assert data.get("providers_total", 0) >= 700


def test_cli_crawl_fmhy():
    runner = CliRunner()
    result = runner.invoke(main, ["--crawl-fmhy"])
    assert result.exit_code == 0
    assert "FMHY LIVE DIRECTORY DEEP-CRAWLER" in result.output
    assert "Total Providers Synced" in result.output


def test_cli_crawl_fmhy_json():
    runner = CliRunner()
    result = runner.invoke(main, ["--crawl-fmhy", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data.get("status") == "success"
    assert data.get("providers_total", 0) >= 700
    assert "sources_crawled" in data


def test_cli_global_search_json(mock_release_item):
    runner = CliRunner()
    with patch("ripper.ripperdb.harvesters.HarvesterDispatcher.federated_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [mock_release_item]
        result = runner.invoke(main, ["-gs", "Inception", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["provider"] == "yts"
        assert "Inception" in data[0]["title"]
        assert data[0]["quality_score"] == 92.5


def test_cli_global_search_auto_watch(mock_release_item, mock_cached_stream):
    runner = CliRunner()
    with patch("ripper.ripperdb.harvesters.HarvesterDispatcher.federated_search", new_callable=AsyncMock) as mock_search, \
         patch("ripper.ripperdb.harvesters.HarvesterDispatcher.resolve_stream_link", new_callable=AsyncMock) as mock_resolve, \
         patch("ripper.ripperdb.bridge.launch_stream_in_player_with_headers") as mock_launch:

        mock_search.return_value = [mock_release_item]
        mock_resolve.return_value = mock_cached_stream
        mock_launch.return_value = (True, "Playing stream")

        result = runner.invoke(main, ["-gs", "Inception", "-w"])
        assert result.exit_code == 0
        mock_launch.assert_called_once()
        assert "Playing stream" in result.output


def test_cli_global_search_auto_download(mock_release_item, mock_cached_stream):
    runner = CliRunner()
    with patch("ripper.ripperdb.harvesters.HarvesterDispatcher.federated_search", new_callable=AsyncMock) as mock_search, \
         patch("ripper.ripperdb.harvesters.HarvesterDispatcher.resolve_stream_link", new_callable=AsyncMock) as mock_resolve, \
         patch("ripper.ripperdb.bridge.download_stream") as mock_download:

        mock_search.return_value = [mock_release_item]
        mock_resolve.return_value = mock_cached_stream
        mock_download.return_value = True

        result = runner.invoke(main, ["-gs", "Inception", "-dl"])
        assert result.exit_code == 0
        mock_download.assert_called_once()
        assert "Resolving stream for top match" in result.output


def test_bridge_launch_stream_in_player_with_headers(mock_cached_stream, tmp_path):
    with patch("ripper.ripperdb.bridge.detect_available_players") as mock_detect, \
         patch("subprocess.Popen") as mock_popen, \
         patch("ripper.ripperdb.bridge.save_playback_resume_state") as mock_resume, \
         patch("httpx.Client.get") as mock_http_get:

        mock_detect.return_value = [("PotPlayer", r"C:\Program Files\DAUM\PotPlayer\PotPlayer64.exe")]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "WEBVTT\n1\n00:00:01.000 --> 00:00:04.000\nHello"
        mock_http_get.return_value = mock_resp

        success, msg = launch_stream_in_player_with_headers(mock_cached_stream, title="Inception")
        assert success is True
        assert "PotPlayer" in msg
        mock_popen.assert_called_once()
        called_args = mock_popen.call_args[0][0]
        assert r"C:\Program Files\DAUM\PotPlayer\PotPlayer64.exe" in called_args[0]
        assert "https://cdn.example.com/hls/master.m3u8" in called_args[1]


def test_bridge_launch_magnet():
    magnet_stream = CachedStream(
        id="magnet_1",
        release_item_id="rel_1",
        direct_url="magnet:?xt=urn:btih:TESTMAG123&dn=Movie",
        quality="1080p",
        expires_at="2030-01-01T00:00:00Z",
    )
    with patch("os.startfile", create=True) as mock_startfile, \
         patch("ripper.ripperdb.bridge.save_playback_resume_state"):
        success, msg = launch_stream_in_player_with_headers(magnet_stream, title="Magnet Movie")
        if sys.platform == "win32":
            assert success is True
            assert "magnet link" in msg.lower()


def test_bridge_download_stream(mock_cached_stream):
    with patch("ripper.ripperdb.bridge.download_file_fast", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = Path("Inception.mp4")
        ok = download_stream(mock_cached_stream, title="Inception", output_dir=".")
        assert ok is True
        mock_dl.assert_called_once()


def test_bridge_format_stream_summary(mock_cached_stream, mock_release_item):
    panel = format_stream_summary(mock_cached_stream, mock_release_item)
    assert panel is not None
    assert panel.title is not None
    assert "Inception" in str(panel.renderable)


@pytest.mark.asyncio
async def test_interactive_handle_global_search_flow(mock_release_item, mock_cached_stream):
    from ripper.interactive import handle_global_search_flow

    with patch("ripper.ripperdb.harvesters.HarvesterDispatcher.federated_search", new_callable=AsyncMock) as mock_search, \
         patch("ripper.ripperdb.harvesters.HarvesterDispatcher.resolve_stream_link", new_callable=AsyncMock) as mock_resolve, \
         patch("ripper.interactive.Prompt.ask") as mock_prompt, \
         patch("ripper.ripperdb.bridge.launch_stream_in_player_with_headers") as mock_player:

        mock_search.return_value = [mock_release_item]
        mock_resolve.return_value = mock_cached_stream
        mock_player.return_value = (True, "Playing in MPV")
        mock_prompt.side_effect = ["", "1", "1", ""]

        await handle_global_search_flow(
            initial_query="Inception",
            season=None,
            episode=None,
            min_quality="1080p",
        )

        mock_search.assert_called_once()
        mock_resolve.assert_called_once()
        mock_player.assert_called_once()
