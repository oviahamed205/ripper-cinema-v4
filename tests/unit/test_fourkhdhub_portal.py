"""
tests.unit.test_fourkhdhub_portal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for 4KHDHub / HubCloud resolver.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from ripper.portals.fourkhdhub import FourKHdHubPortal


def test_fourkhdhub_domain_matching():
    portal = FourKHdHubPortal()
    assert portal.can_handle("https://4khdhub.dad/movie-123") is True
    assert portal.can_handle("https://hubcloud.php/drive/xyz") is True
    assert portal.can_handle("https://gamerxyt.com/watch") is True
    assert portal.can_handle("https://randomsite.org/video") is False


def test_pixeldrain_url_conversion():
    raw = "https://pixeldrain.com/u/k8dJ12wZ"
    api_url = FourKHdHubPortal.pixeldrain_to_api_url(raw)
    assert api_url == "https://pixeldrain.com/api/file/k8dJ12wZ"

    already_api = "https://pixeldrain.com/api/file/k8dJ12wZ"
    assert FourKHdHubPortal.pixeldrain_to_api_url(already_api) == already_api


def test_unwrap_watch_online_url():
    wrapped = "https://example.com/redirect?url=https%3A%2F%2Fpixeldrain.com%2Fu%2Fabc12345"
    unwrapped = FourKHdHubPortal.unwrap_watch_online_url(wrapped)
    assert unwrapped == "https://pixeldrain.com/u/abc12345"

    clean = "https://direct.com/video.mp4"
    assert FourKHdHubPortal.unwrap_watch_online_url(clean) is None


@pytest.mark.asyncio
async def test_fourkhdhub_resolve_html():
    portal = FourKHdHubPortal()
    sample_html = """
    <html>
        <body>
            <a id="download" href="https://hubcloud.php/download/xyz">Download</a>
            <a href="https://pixeldrain.com/u/98765432">PixelDrain Mirror</a>
            <a href="https://streamtape.com/v/abcd/video.mp4">StreamTape</a>
        </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sample_html

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    results = await portal.resolve(mock_client, "https://4khdhub.dad/movie-100")
    assert len(results) >= 2
    urls = [r.direct_url for r in results]
    assert "https://pixeldrain.com/api/file/98765432" in urls
    assert "https://streamtape.com/v/abcd/video.mp4" in urls
