"""
tests.test_camoufox_integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integration and resilience tests for the Camoufox upgrades across
AnyStream decoders and browser bypass modules.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ripper.anystream.decoders.html5_generic import HTML5GenericDecoder
from ripper.anystream.engine import AnyStreamEngine
from ripper.anystream.base_decoder import StreamInfo
from ripper.media import MediaDownloadItem
from ripper.browser_bypass import (
    _safe_click_continue,
    _CLEARANCE_COOKIE_CACHE,
    _html_still_challenged,
    is_honeypot_url,
)


# =============================================================================
# 1. AnyStream HTML5GenericDecoder + Camoufox Fallback Tests
# =============================================================================

@pytest.mark.asyncio
async def test_html5_generic_decoder_static_hit():
    decoder = HTML5GenericDecoder()
    html = """
    <html>
      <body>
        <video src="https://storage.example.com/video.mp4" controls></video>
      </body>
    </html>
    """
    info = await decoder.decode("https://example.com/watch", html=html)
    assert info is not None
    assert info.stream_url == "https://storage.example.com/video.mp4"
    assert info.format == "mp4"


@pytest.mark.asyncio
async def test_html5_generic_decoder_camoufox_fallback():
    decoder = HTML5GenericDecoder()
    # Heavily obfuscated HTML with zero static video tags or plaintext urls
    obfuscated_html = """
    <html>
      <body>
        <div id="player-container"></div>
        <script>
          // Dynamic WASM player blob loader
          var _0x9f1a = ["aW5pdGlhbGl6ZQ=="];
        </script>
      </body>
    </html>
    """
    mock_sniffed_items = [
        MediaDownloadItem(
            title="Sniffed 1080p Stream",
            movie_name="Sniffed Movie",
            quality="1080p",
            codec="WEB-DL",
            size_str="1.8GB",
            audio_info="",
            short_link="https://fastdl.cloud/stream.m3u8",
            unshortened_landing_url="https://fastdl.cloud/stream.m3u8",
        )
    ]

    with patch("ripper.healer.camoufox_sniffer.CamoufoxStreamSniffer.sniff_and_extract", new=AsyncMock(return_value=mock_sniffed_items)):
        info = await decoder.decode("https://obfuscated-host.com/play", html=obfuscated_html)
        assert info is not None
        assert info.stream_url == "https://fastdl.cloud/stream.m3u8"
        assert info.format == "hls"
        assert info.host_name == "Camoufox Wire Stream"


@pytest.mark.asyncio
async def test_anystream_engine_integration_fallback():
    engine = AnyStreamEngine()
    obfuscated_html = "<html><body><div id='wasm-player'></div></body></html>"
    mock_sniffed = [
        MediaDownloadItem(
            title="Wire Captured Stream",
            movie_name="Wire Movie",
            quality="1080p",
            codec="WEB-DL",
            size_str="2.4GB",
            audio_info="",
            short_link="https://storage.cdn.com/master.m3u8",
            unshortened_landing_url="https://storage.cdn.com/master.m3u8",
        )
    ]

    with patch("ripper.healer.camoufox_sniffer.CamoufoxStreamSniffer.sniff_and_extract", new=AsyncMock(return_value=mock_sniffed)):
        stream = await engine.extract_stream("https://protected-stream.com/view", html=obfuscated_html)
        assert stream is not None
        assert stream.stream_url == "https://storage.cdn.com/master.m3u8"
        assert stream.format == "hls"


# =============================================================================
# 2. Browser Bypass Semantic Clicker & Honeypot Tests
# =============================================================================

@pytest.mark.asyncio
async def test_browser_bypass_safe_click_positive():
    mock_page = MagicMock()

    # Create mock button for query_selector (fast path) returning None
    mock_page.query_selector = AsyncMock(return_value=None)

    # Create candidates for query_selector_all (semantic fallback)
    btn_honeypot = MagicMock()
    btn_honeypot.inner_text = AsyncMock(return_value="Download APK Now")
    btn_honeypot.get_attribute = AsyncMock(side_effect=lambda a: "https://vegamovies-apk.com/trap" if a == "href" else "")
    btn_honeypot.click = AsyncMock()

    btn_legit = MagicMock()
    btn_legit.inner_text = AsyncMock(return_value="Click Here to Proceed")
    btn_legit.get_attribute = AsyncMock(side_effect=lambda a: "https://hubcloud.club/drive/proceed" if a == "href" else "")
    btn_legit.click = AsyncMock()

    mock_page.query_selector_all = AsyncMock(return_value=[btn_honeypot, btn_legit])

    await _safe_click_continue(mock_page)

    # Verify honeypot was NOT clicked and legit proceed button WAS clicked
    btn_honeypot.click.assert_not_called()
    btn_legit.click.assert_called_once()


def test_clearance_cookie_cache_domain_storage():
    domain = "hubcloud.club"
    _CLEARANCE_COOKIE_CACHE[domain] = [
        {"name": "cf_clearance", "value": "test_token_abc123", "domain": "hubcloud.club"}
    ]
    assert domain in _CLEARANCE_COOKIE_CACHE
    assert _CLEARANCE_COOKIE_CACHE[domain][0]["value"] == "test_token_abc123"
