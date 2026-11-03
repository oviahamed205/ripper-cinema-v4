"""
Unit tests verifying VegaMovies NexDrive full server mirror resolution,
FastDL Google CDN direct extraction, and anti-honeypot trap filtering.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from ripper.models import ServerMirror
from ripper.resolver.core import FetchResult
from ripper.resolver.core.honeypot_filter import is_ad_trap
from ripper.resolver.handlers.nexdrive import resolve_nexdrive_page, resolve_fastdl_page


SAMPLE_NEXDRIVE_HTML = """
<!DOCTYPE html>
<html>
<head><title>NexDrive - Download</title></head>
<body>
  <div class="banner">
    <a href="https://vglist.cv" style="color: #ff0000;">VgList.cv</a>
  </div>
  <div class="download-box">
    <a href="https://fastdl.zip/embed?download=sampletoken123" rel="nofollow">
      <button class="btn btn-sm">⚡ G-Direct [Instant]</button>
    </a>
    <a href="https://vcloud.fit/samplevcloud" rel="nofollow">
      <button class="btn btn-sm">⚡ V-Cloud [Resumable]</button>
    </a>
    <a href="https://filebee.xyz/file/samplefilebee" rel="nofollow">
      <button class="btn btn-sm">⚡ Filepress [G-Drive]</button>
    </a>
    <a href="https://new26.gdtot.dad/file/samplegdtot" rel="nofollow">
      <button class="btn btn-sm">⚡ GDToT [G-Drive]</button>
    </a>
    <a href="https://dgdrive.pro/sampledgdrive" rel="nofollow">
      <button class="btn btn-sm">DropGalaxy</button>
    </a>
  </div>
</body>
</html>
"""

SAMPLE_FASTDL_HTML = """
<html>
<head><title>redirecting ...</title></head>
<body>
redirecting..
<script>
var reurl = "https://fastdl.zip/dl.php?link=https://video-downloads.googleusercontent.com/SAMPLE_DIRECT_GOOGLE_STREAM_TOKEN";
</script>
</body>
</html>
"""


def test_honeypot_filter_blocks_sponsor_traps():
    """Verify that is_ad_trap catches vglist and vegamovies ad/sponsor domains."""
    assert is_ad_trap("https://vglist.cv") is True
    assert is_ad_trap("https://vglist.top/landing") is True
    assert is_ad_trap("https://vegamovies-apk.com/") is True
    assert is_ad_trap("https://vegamovies.click/") is True
    assert is_ad_trap("https://fastdl.zip/embed?download=xyz") is False
    assert is_ad_trap("https://vcloud.fit/5daf_az") is False


@pytest.mark.anyio
async def test_resolve_fastdl_page_extracts_google_stream():
    """Verify resolve_fastdl_page extracts direct Google UserContent stream."""
    mock_client = AsyncMock()

    with patch("ripper.resolver.handlers.nexdrive.request_capped_with_client") as mock_fetch:
        mock_fetch.return_value = FetchResult(
            status_code=200,
            url="https://fastdl.zip/embed?download=sampletoken123",
            text=SAMPLE_FASTDL_HTML,
            headers={"content-type": "text/html"},
        )
        mirror = await resolve_fastdl_page(mock_client, "https://fastdl.zip/embed?download=sampletoken123", {})
        assert mirror is not None
        assert mirror.direct_download_url == "https://video-downloads.googleusercontent.com/SAMPLE_DIRECT_GOOGLE_STREAM_TOKEN"
        assert "G-Direct" in mirror.label
        assert mirror.server_type == "Google High-Speed Direct"


@pytest.mark.anyio
async def test_resolve_nexdrive_page_unrolls_all_mirrors_and_drops_vglist():
    """Verify resolve_nexdrive_page extracts all 5 servers and strictly drops vglist.cv."""
    mock_client = AsyncMock()

    async def mock_fetch_impl(client, url, headers, timeout, follow_redirects=True):
        if "nexdrive" in url:
            return FetchResult(status_code=200, url=url, text=SAMPLE_NEXDRIVE_HTML, headers={})
        elif "fastdl" in url:
            return FetchResult(status_code=200, url=url, text=SAMPLE_FASTDL_HTML, headers={})
        return FetchResult(status_code=200, url=url, text="<html>OK</html>", headers={})

    with patch("ripper.resolver.handlers.nexdrive.request_capped_with_client", side_effect=mock_fetch_impl):
        with patch("ripper.resolver.handlers.nexdrive.resolve_vcloud_page") as mock_vcloud:
            mock_vcloud.return_value = [
                ServerMirror(
                    label="VegaCloud [Download [FSLv2 Server]]",
                    intermediate_url="https://vcloud.fit/samplevcloud",
                    direct_download_url="https://r2.storage/video.mkv",
                    server_type="Cloudflare R2 Stream",
                ),
                ServerMirror(
                    label="VegaCloud [Download [PixelServer : 2]]",
                    intermediate_url="https://vcloud.fit/samplevcloud",
                    direct_download_url="https://pixeldrain.com/api/file/abc?download",
                    server_type="PixelDrain Direct",
                ),
            ]

            mirrors = await resolve_nexdrive_page(mock_client, "https://nexdrive.fit/genxfm784776388440/", {})
            assert len(mirrors) >= 5
            labels = [m.label for m in mirrors]
            urls = [m.direct_download_url or m.intermediate_url for m in mirrors]

            # Verify G-Direct is present and resolved
            assert any("G-Direct" in l for l in labels)
            # Verify VCloud mirrors are present
            assert any("FSLv2" in l for l in labels)
            assert any("PixelServer" in l for l in labels)
            # Verify Filepress, GDToT, DropGalaxy are present
            assert any("Filepress" in l for l in labels)
            assert any("GDToT" in l for l in labels)
            assert any("DropGalaxy" in l for l in labels)

            # STRICT GUARANTEE: vglist.cv MUST NEVER be in URLs or labels
            assert not any("vglist" in u.lower() for u in urls)
            assert not any("vglist" in l.lower() for l in labels)
