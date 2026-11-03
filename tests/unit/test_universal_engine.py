"""
Unit and integration tests for ripper.universal_engine.
Validates:
- Semantic heuristic token scoring & DOM tree clustering
- Anti-ad and noise filtering
- Stream MIME & packet sniffing classifier
- Firecrawl cloud scraper parser
- LLM structural condensing
- Multi-tier cascading fallback orchestration
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from ripper.media import MediaDownloadItem
from ripper.universal_engine.heuristics import SemanticHeuristicExtractor
from ripper.universal_engine.sniffer import (
    HeadlessStreamSniffer,
    VIDEO_MIME_TYPES,
    VIDEO_EXTENSIONS,
    CLICK_TARGET_REGEX,
)
from ripper.universal_engine.firecrawl_bridge import FirecrawlCloudBridge
from ripper.universal_engine.llm_extractor import LLMStructuralExtractor
from ripper.universal_engine.pipeline import UniversalPipeline


@pytest.fixture
def heuristic_extractor():
    return SemanticHeuristicExtractor(base_url="https://unknown-movie-hub.org")


def test_heuristic_token_scoring(heuristic_extractor):
    score, meta = heuristic_extractor.score_text_for_media(
        "Download Gladiator II (2024) 4K UHD Remux [24.5 GB] Dual Audio DD5.1"
    )
    assert score >= 0.7
    assert meta["quality"] == "2160P"
    assert "REMUX" in meta["codec"]
    assert meta["size_str"] == "24.5GB"
    assert meta["audio"] == "Dual Audio"


def test_heuristic_exclusion_filtering(heuristic_extractor):
    assert not heuristic_extractor.is_valid_media_href("https://facebook.com/sharer")
    assert not heuristic_extractor.is_valid_media_href("/privacy-policy")
    assert not heuristic_extractor.is_valid_media_href("/dmca-contact")
    assert not heuristic_extractor.is_valid_media_href("#download-section")
    assert not heuristic_extractor.is_valid_media_href("javascript:void(0)")
    assert heuristic_extractor.is_valid_media_href("https://links.kmhd.me/file/abc123")
    assert heuristic_extractor.is_valid_media_href("https://drive.google.com/uc?id=xyz")


def test_heuristic_extraction_card_layout(heuristic_extractor):
    html = """
    <html>
    <head><title>Oppenheimer (2023) Full Movie Download</title></head>
    <body>
      <h1>Oppenheimer (2023)</h1>
      <div class="downloads">
        <div class="box">
          <h3>1080p BluRay HEVC [3.2 GB]</h3>
          <p><a href="https://cloud.storage/oppenheimer_1080p">Download 1080p Cloud Mirror</a></p>
        </div>
        <div class="box">
          <h3>720p HD [1.2 GB]</h3>
          <p><a href="https://cloud.storage/oppenheimer_720p">Download 720p Cloud Mirror</a></p>
        </div>
      </div>
    </body>
    </html>
    """
    items = heuristic_extractor.extract_items(html)
    assert len(items) == 2
    assert items[0].quality == "1080P"
    assert items[0].size_str == "3.2GB"
    assert items[0].short_link == "https://cloud.storage/oppenheimer_1080p"
    assert items[1].quality == "720P"
    assert items[1].size_str == "1.2GB"


def test_heuristic_extraction_table_layout(heuristic_extractor):
    html = """
    <html>
    <head><title>Deadpool & Wolverine 2024</title></head>
    <body>
      <h2>Deadpool & Wolverine</h2>
      <table>
        <tr><th>Format</th><th>Size</th><th>Link</th></tr>
        <tr><td>4k 2160p HDR</td><td>18.4 GB</td><td><a href="https://hub.example/dp4k">Mirror 1</a></td></tr>
        <tr><td>1080p WEB-DL</td><td>2.1 GB</td><td><a href="https://hub.example/dp1080">Mirror 2</a></td></tr>
      </table>
    </body>
    </html>
    """
    items = heuristic_extractor.extract_items(html)
    assert len(items) == 2
    assert items[0].quality == "2160P"
    assert items[0].size_str == "18.4GB"
    assert items[1].quality == "1080P"
    assert items[1].size_str == "2.1GB"


def test_sniffer_mime_and_extension_classification():
    assert "video/mp4" in VIDEO_MIME_TYPES
    assert "application/x-mpegurl" in VIDEO_MIME_TYPES
    assert ".m3u8" in VIDEO_EXTENSIONS
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".mkv" in VIDEO_EXTENSIONS

    assert CLICK_TARGET_REGEX.search("Click Here to Download")
    assert CLICK_TARGET_REGEX.search("Fast Download Link")
    assert CLICK_TARGET_REGEX.search("Proceed to Verification")
    assert not CLICK_TARGET_REGEX.search("Read Privacy Terms")


@pytest.mark.anyio
async def test_firecrawl_bridge_parsing():
    bridge = FirecrawlCloudBridge(api_key="fc-test-key")
    mock_response = {
        "success": True,
        "data": {
            "html": """
            <div>
              <h3>Avatar 2 (2022) 1080p Dual Audio [2.8 GB]</h3>
              <a href="https://download.cloud/avatar1080">Direct Link</a>
            </div>
            """,
            "markdown": "[Download 720p [1.1 GB]](https://download.cloud/avatar720)"
        }
    }

    mock_client = AsyncMock()
    mock_resp_obj = MagicMock()
    mock_resp_obj.status_code = 200
    mock_resp_obj.json.return_value = mock_response
    mock_client.post.return_value = mock_resp_obj

    items = await bridge.scrape_and_extract("https://movie-site.example/avatar2", client=mock_client)
    assert len(items) >= 1
    assert any(it.quality == "1080P" for it in items)


def test_llm_extractor_condensing():
    llm = LLMStructuralExtractor(api_key="test-key")
    raw_html = """
    <html>
      <head><style>.ad{color:red;}</style></head>
      <body>
        <script>console.log("ad code");</script>
        <h1>Godzilla x Kong 2024</h1>
        <p>Movie description goes here</p>
        <a href="https://drive.link/gxk1080">1080p Links [2.5GB]</a>
      </body>
    </html>
    """
    condensed = llm.condense_html(raw_html)
    assert "console.log" not in condensed
    assert "Godzilla x Kong 2024" in condensed
    assert "https://drive.link/gxk1080" in condensed


@pytest.mark.anyio
async def test_universal_pipeline_cascade():
    pipeline = UniversalPipeline()

    # Synthetic HTML that misses Tier 0 but hits Tier 1 Heuristics
    html = """
    <html>
    <head><title>Alien Romulus (2024)</title></head>
    <body>
      <h2>Alien: Romulus (2024) IMAX</h2>
      <div class="custom-tier">
        <a href="https://stream.fast/file/alien_1080p">Download 1080p x265 [2.1 GB]</a>
      </div>
      <div class="custom-tier">
        <a href="https://stream.fast/file/alien_720p">Download 720p HD [1.1 GB]</a>
      </div>
    </body>
    </html>
    """
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_resp.headers = {}
    mock_client.get.return_value = mock_resp
    mock_client.head.return_value = mock_resp

    items = await pipeline.extract("https://alien-movie.fake", html=html, client=mock_client)
    assert len(items) == 2
    assert items[0].quality == "1080P"
    assert items[0].size_str == "2.1GB"
    assert items[1].quality == "720P"
    assert items[1].size_str == "1.1GB"


@pytest.mark.anyio
async def test_universal_pipeline_deduplication():
    from ripper.universal_engine import universal_extract_media
    html = """
    <html>
    <head><title>Gladiator 2</title></head>
    <body>
      <h2>Gladiator 2</h2>
      <a href="https://dl.cdn/g2_1080p">Download 1080p [2.5 GB]</a>
      <a href="https://dl.cdn/g2_1080p">Download 1080p [2.5 GB]</a>
    </body>
    </html>
    """
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_client.get.return_value = mock_resp
    mock_client.head.return_value = mock_resp

    items = await universal_extract_media("https://gladiator.test", html=html, client=mock_client)
    assert len(items) == 1
    assert items[0].quality == "1080P"
    assert items[0].size_str == "2.5GB"
