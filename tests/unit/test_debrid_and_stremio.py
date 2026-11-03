"""
tests.unit.test_debrid_and_stremio
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for Stremio HTTP Addons and Real-Debrid / Torrentio clients.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from ripper.stremio_addons import StremioAddonClient, StremioStream, AddonManifest
from ripper.debrid import RealDebridClient, TorrentioClient, DebridStreamResult


def test_stremio_url_normalization():
    raw1 = "stremio://torrentio.strem.fun/manifest.json"
    assert StremioAddonClient.normalize_manifest_url(raw1) == "https://torrentio.strem.fun/manifest.json"

    raw2 = "torrentio.strem.fun"
    assert StremioAddonClient.normalize_manifest_url(raw2) == "https://torrentio.strem.fun/manifest.json"

    raw3 = "https://addon.example.com/"
    assert StremioAddonClient.normalize_manifest_url(raw3) == "https://addon.example.com/manifest.json"


def test_stremio_base_url_extraction():
    url = "https://torrentio.strem.fun/manifest.json"
    assert StremioAddonClient.get_base_addon_url(url) == "https://torrentio.strem.fun"


@pytest.mark.asyncio
async def test_torrentio_metadata_parsing():
    client = TorrentioClient()
    mock_data = {
        "streams": [
            {
                "name": "Torrentio\n[RD+] 4K",
                "title": "Interstellar.2014.2160p.UHD.BluRay.x265.TrueHD.Atmos.7.1-SWTYBLZ\n👤 450 💾 42.5 GB",
                "url": "https://debrid.example.com/stream/xyz",
                "infoHash": "abc123hash",
            },
            {
                "name": "Torrentio\n1080p",
                "title": "Interstellar.2014.1080p.BluRay.x264.DTS-HD.MA.5.1\n👤 120 💾 12.8 GB",
                "infoHash": "def456hash",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=mock_data)

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        releases = await client.resolve("tt0816692", media_type="movie")
        assert len(releases) == 2

        r1 = releases[0]
        assert r1.quality == "2160P" or r1.quality == "4K"
        assert r1.seeders == 450
        assert r1.size_bytes > 40 * 1024 * 1024 * 1024  # > 40GB
        assert r1.is_cached is True
        assert r1.codec == "x265"
        assert r1.audio in ("TrueHD", "Atmos")

        r2 = releases[1]
        assert r2.quality == "1080P"
        assert r2.seeders == 120
        assert r2.is_cached is False


@pytest.mark.asyncio
async def test_realdebrid_unrestrict():
    rd = RealDebridClient(api_key="test_key_123")
    mock_data = {
        "download": "https://1fichier.rd.com/direct/video.mp4",
        "filename": "movie.mp4",
        "filesize": 1073741824,
        "mimeType": "video/mp4",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=mock_data)

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        res = await rd.unrestrict_link("https://1fichier.com/?abcdef")
        assert res is not None
        assert res.stream_url == "https://1fichier.rd.com/direct/video.mp4"
        assert res.filename == "movie.mp4"
        assert res.filesize_bytes == 1073741824
