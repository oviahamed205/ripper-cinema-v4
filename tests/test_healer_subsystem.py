"""
tests.test_healer_subsystem
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Comprehensive test suite for the autonomous scraper self-healing subsystem.
Validates AnomalyDetector, DynamicRegistry, DOMPruner, CamoufoxStreamSniffer,
LLMDiagnostics, and AutoHealer Orchestrator.
"""

from __future__ import annotations

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ripper.media import MediaDownloadItem
from ripper.models import ServerMirror
from ripper.healer import (
    AnomalyDetector,
    AnomalyType,
    AutoHealer,
    CamoufoxStreamSniffer,
    DOMPruner,
    DynamicRegistry,
    ExtractionAnomaly,
    HealedResult,
    HealerConfig,
    HealingStrategy,
    LLMDiagnostics,
    self_healing_extract,
)


def _make_item(
    title: str = "Test Movie [1080p]",
    movie_name: str = "Test Movie",
    quality: str = "1080p",
    codec: str = "WEB-DL",
    size_str: str = "2.1GB",
    short_link: str = "https://fastdl.cloud/file",
    servers: list = None,
) -> MediaDownloadItem:
    return MediaDownloadItem(
        title=title,
        movie_name=movie_name,
        quality=quality,
        codec=codec,
        size_str=size_str,
        audio_info="",
        short_link=short_link,
        unshortened_landing_url=short_link,
        servers=servers or [],
    )


# =============================================================================
# 1. AnomalyDetector Unit Tests
# =============================================================================

def test_anomaly_detector_healthy_extraction():
    detector = AnomalyDetector()
    items = [
        _make_item(
            title="Test Movie 2026 [1080p]",
            movie_name="Test Movie 2026",
            short_link="https://fastdl.cloud/stream",
            servers=[ServerMirror(label="FastDL", intermediate_url="https://fastdl.cloud/stream")],
        )
    ]
    html = "<html><body><h1>Test Movie 2026</h1><a href='https://fastdl.cloud/stream'>1080p Download</a></body></html>"
    anomaly = detector.diagnose("https://vegamovies.mex/movie", html=html, status_code=200, items=items)
    assert anomaly is None


def test_anomaly_detector_zero_items_known_hoster():
    detector = AnomalyDetector()
    html = "<html><body><h1>Mutated Vega Layout</h1><div class='x9f_random'>Nothing here</div></body></html>"
    anomaly = detector.diagnose("https://vegamovies.mex/movie-123", html=html, status_code=200, items=[])
    assert anomaly is not None
    assert anomaly.anomaly_type == AnomalyType.ZERO_ITEMS
    assert "Zero download items" in anomaly.reason


def test_anomaly_detector_honeypot_detection_and_filtering():
    detector = AnomalyDetector()
    honeypot_item = _make_item(
        title="Fake APK Download",
        movie_name="Fake APK Download",
        short_link="https://vglist.cv/watch/video123",
        servers=[ServerMirror(label="Ad Trap", intermediate_url="https://vglist.cv/click")],
    )
    legit_item = _make_item(
        title="Legit Movie [1080p]",
        movie_name="Legit Movie",
        short_link="https://fastdl.cloud/file",
        servers=[ServerMirror(label="FastDL", intermediate_url="https://fastdl.cloud/file")],
    )
    items = [honeypot_item, legit_item]
    anomaly = detector.diagnose("https://vegamovies.mex/movie", html="", status_code=200, items=items)
    assert anomaly is not None
    assert anomaly.anomaly_type == AnomalyType.HONEYPOT_DETECTED
    assert len(anomaly.flagged_urls) > 0

    # Test safe filtering
    clean = detector.filter_safe_items(items)
    assert len(clean) == 1
    assert clean[0].movie_name == "Legit Movie"


def test_anomaly_detector_cloudflare_turnstile():
    detector = AnomalyDetector()
    cf_html = """
    <html>
      <head><title>Just a moment...</title></head>
      <body>
        <div id="cf-browser-verification">
          <div class="cf-chl-widget">Verifying you are human...</div>
        </div>
      </body>
    </html>
    """
    anomaly = detector.diagnose("https://hubcloud.club/drive/123", html=cf_html, status_code=403, items=[])
    assert anomaly is not None
    assert anomaly.anomaly_type == AnomalyType.CLOUDFLARE_BLOCKED


def test_anomaly_detector_rate_limiting():
    detector = AnomalyDetector()
    anomaly = detector.diagnose("https://fastdl.cloud/file", html="Too Many Requests", status_code=429, items=[])
    assert anomaly is not None
    assert anomaly.anomaly_type == AnomalyType.RATE_LIMITED


# =============================================================================
# 2. DynamicRegistry Unit Tests
# =============================================================================

def test_dynamic_registry_persistence_and_aliases():
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_file = os.path.join(tmpdir, "test_registry.json")
        registry = DynamicRegistry(reg_file)

        # Domain alias test
        registry.map_domain_alias("vegamovies.im", "vegamovies.mex")
        assert registry.get_domain_alias("vegamovies.im") == "vegamovies.mex"
        assert registry.get_domain_alias("https://vegamovies.im/movie/123") == "vegamovies.mex"

        # Blacklist test
        registry.add_to_blacklist("fake-stream-trap.xyz")
        assert registry.is_blacklisted("https://fake-stream-trap.xyz/ad") is True
        assert registry.is_blacklisted("https://fastdl.cloud/file") is False

        # Strategy promotion test
        registry.record_success("vegamovies.mex", HealingStrategy.TIER_2_CAMOUFOX, latency_ms=120.0)
        promoted = registry.get_promoted_strategies("vegamovies.mex")
        assert len(promoted) >= 1
        assert promoted[0] == HealingStrategy.TIER_2_CAMOUFOX

        # Promote another strategy
        registry.record_success("vegamovies.mex", HealingStrategy.TIER_4_LOCAL_GGUF, latency_ms=45.0)
        promoted_after = registry.get_promoted_strategies("vegamovies.mex")
        assert promoted_after[0] == HealingStrategy.TIER_4_LOCAL_GGUF
        assert promoted_after[1] == HealingStrategy.TIER_2_CAMOUFOX

        # Reload from disk to verify atomic persistence
        reloaded = DynamicRegistry(reg_file)
        assert reloaded.get_domain_alias("vegamovies.im") == "vegamovies.mex"
        assert reloaded.is_blacklisted("https://fake-stream-trap.xyz/test") is True


# =============================================================================
# 3. DOMPruner Unit Tests
# =============================================================================

def test_dom_pruner_semantic_compression():
    pruner = DOMPruner(max_bytes=4096)
    bloated_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Movie Download</title>
        <style>.ads { color: red; } body { margin: 0; }</style>
        <script>var tracker = function() { console.log("analytics"); };</script>
      </head>
      <body>
        <!-- Header comment -->
        <header><nav><a href="/home">Home</a><a href="/about">About</a></nav></header>
        <svg><path d="M10 10"/></svg>
        <div class="content">
          <h2>Avatar 2: The Way of Water (2022) Multi-Audio [Hindi-Eng]</h2>
          <div class="downloads">
            <a href="https://vglist.cv/trap123">Download Fake APK</a>
            <a href="https://fastdl.cloud/file/avatar-1080p">Download 1080p 10Bit [FastDL] (2.8GB)</a>
            <a href="https://hubcloud.club/drive/avatar-720p">Episode 1 Download 720p [HubCloud]</a>
          </div>
        </div>
        <footer><p>Copyright 2026</p></footer>
      </body>
    </html>
    """
    pruned = pruner.prune(bloated_html)
    assert len(pruned) < len(bloated_html)
    assert "[H2] Avatar 2: The Way of Water" in pruned
    assert "fastdl.cloud/file/avatar-1080p" in pruned
    assert "hubcloud.club/drive/avatar-720p" in pruned
    assert "vglist.cv" not in pruned  # Honeypot filtered
    assert "<script>" not in pruned
    assert "<style>" not in pruned


# =============================================================================
# 4. CamoufoxStreamSniffer Unit Tests
# =============================================================================

def test_camoufox_sniffer_binary_detection():
    config = HealerConfig()
    sniffer = CamoufoxStreamSniffer(config)
    # Binary should be detected if exists on disk
    bin_path = sniffer._resolve_camoufox_executable()
    if os.path.isfile(r"D:\camoufox-152.0.4-beta.28-win.i686\camoufox.exe"):
        assert bin_path == r"D:\camoufox-152.0.4-beta.28-win.i686\camoufox.exe"


# =============================================================================
# 5. LLMDiagnostics Unit Tests
# =============================================================================

def test_llm_diagnostics_json_parser():
    diag = LLMDiagnostics()
    sample_model_response = """
    Here are the extracted links:
    ```json
    [
      {
        "movie_name": "Inception (2010)",
        "quality": "1080p BluRay",
        "size_str": "2.4GB",
        "url": "https://fastdl.cloud/inception-1080p",
        "server_name": "FastDL"
      },
      {
        "movie_name": "Fake APK",
        "quality": "HD",
        "size_str": "15MB",
        "url": "https://vegamovies-apk.com/app.apk",
        "server_name": "Adware"
      }
    ]
    ```
    Hope this helps!
    """
    items = diag._parse_json_items(sample_model_response, "https://test.com")
    assert len(items) == 1
    assert items[0].movie_name == "Inception (2010)"
    assert items[0].quality == "1080p BluRay"
    assert items[0].short_link == "https://fastdl.cloud/inception-1080p"


def test_llm_diagnostics_pruned_heuristic_fallback():
    diag = LLMDiagnostics()
    pruned_text = """
    [H1] Dune: Part Two (2024)
    LINK: FastDL 1080p Web-DL [2.1GB] -> https://fastdl.cloud/dune2-1080p
    LINK: HubCloud 720p HD -> https://hubcloud.club/dune2-720p
    """
    items = diag._heuristic_fallback(pruned_text, "https://test.com")
    assert len(items) == 2
    assert items[0].movie_name == "Dune: Part Two (2024)"
    assert items[0].quality == "1080P"
    assert items[0].servers[0].label == "FastDL"
    assert items[1].quality == "720P"
    assert items[1].servers[0].label == "HubCloud"


# =============================================================================
# 6. AutoHealer End-to-End Orchestration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_auto_healer_fast_path_healthy():
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_file = os.path.join(tmpdir, "healer_reg.json")
        config = HealerConfig(registry_file=reg_file)
        healer = AutoHealer(config)

        # Mock standard extract returning valid items
        clean_html = """
        <html>
          <h3>Spider-Man 2026</h3>
          <a href="https://fastdl.cloud/spiderman-1080p">Download 1080p</a>
        </html>
        """
        with patch("ripper.healer.orchestrator.extract_media_items_from_html") as mock_extract:
            mock_extract.return_value = [
                _make_item(
                    title="Spider-Man 2026 [1080p]",
                    movie_name="Spider-Man 2026",
                    short_link="https://fastdl.cloud/spiderman-1080p",
                )
            ]
            result = await healer.heal("https://vegamovies.mex/spiderman", html=clean_html)
            assert result.success is True
            assert result.strategy_used == HealingStrategy.TIER_1_HEURISTICS
            assert len(result.items) == 1


@pytest.mark.asyncio
async def test_auto_healer_cascade_on_zero_items_mutation():
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_file = os.path.join(tmpdir, "healer_reg.json")
        config = HealerConfig(registry_file=reg_file)
        healer = AutoHealer(config)

        # Simulate standard extract returning 0 items (DOM mutation)
        mutated_html = "<html><body><h1>Mutated Host</h1><div class='m9_xyz'>Click</div></body></html>"

        # Mock sniffer successfully recovering via Tier 2 Camoufox
        mock_sniffed_items = [
            _make_item(
                title="Recovered Media [1080p]",
                movie_name="Recovered Media",
                short_link="https://fastdl.cloud/stream.mp4",
                servers=[ServerMirror(label="Camoufox Sniffer", intermediate_url="https://fastdl.cloud/stream.mp4")],
            )
        ]
        with patch("ripper.healer.orchestrator.extract_media_items_from_html", return_value=[]):
            with patch.object(healer.sniffer, "sniff_and_extract", new=AsyncMock(return_value=mock_sniffed_items)):
                result = await healer.heal("https://vegamovies.mex/mutated-page", html=mutated_html)
                assert result.success is True
                assert result.strategy_used == HealingStrategy.TIER_2_CAMOUFOX
                assert len(result.items) == 1
                assert result.cached_to_registry is True

                # Verify strategy was promoted in registry
                promoted = healer.registry.get_promoted_strategies("vegamovies.mex")
                assert promoted[0] == HealingStrategy.TIER_2_CAMOUFOX


@pytest.mark.asyncio
async def test_self_healing_extract_decorator():
    mock_items = [
        _make_item(
            title="Decorated Item [1080p]",
            movie_name="Decorated Item",
            short_link="https://fastdl.cloud/file",
        )
    ]

    @self_healing_extract
    async def sample_extractor(url: str):
        return mock_items

    items = await sample_extractor("https://example.com/test")
    assert len(items) == 1
    assert items[0].movie_name == "Decorated Item"
