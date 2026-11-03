"""
tests.unit.test_moviebox_portal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for MovieBox Mobile BFF portal, HMAC signing, and stream extraction.
"""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from ripper.portals.moviebox import (
    generate_x_client_token,
    build_canonical_string,
    generate_x_tr_signature,
    parse_jwt_claims,
    MovieBoxSession,
    MovieBoxPortal,
)


def test_generate_x_client_token():
    ts = 1726000000000
    token = generate_x_client_token(ts)
    parts = token.split(",")
    assert len(parts) == 2
    assert parts[0] == str(ts)
    assert len(parts[1]) == 32  # 32-char hex MD5


def test_build_canonical_string():
    canonical = build_canonical_string(
        method="GET",
        accept="application/json",
        content_type="application/json",
        url_str="https://api6.aoneroom.com/wefeed-mobile-bff/vod-api/detail?subjectId=123&foo=bar",
        body=None,
        timestamp_ms=1726000000000,
    )
    lines = canonical.split("\n")
    assert len(lines) == 7
    assert lines[0] == "GET"
    assert lines[1] == "application/json"
    assert lines[2] == "application/json"
    assert lines[3] == ""  # empty body length
    assert lines[4] == "1726000000000"
    assert lines[5] == ""  # empty body hash
    assert lines[6] == "/wefeed-mobile-bff/vod-api/detail?foo=bar&subjectId=123"  # sorted query


def test_generate_x_tr_signature():
    sig = generate_x_tr_signature(
        method="POST",
        accept="application/json",
        content_type="application/json",
        url_str="https://api6.aoneroom.com/wefeed-mobile-bff/vod-api/search",
        body='{"keyword":"avatar"}',
        timestamp_ms=1726000000000,
    )
    parts = sig.split("|")
    assert len(parts) == 3
    assert parts[0] == "1726000000000"
    assert parts[1] == "2"
    assert len(parts[2]) > 10  # base64 signature


def test_parse_jwt_claims():
    # Valid sample JWT payload: {"userId": "usr_9988", "exp": 1890000000}
    # base64 of payload: eyJ1c2VySWQiOiAidXNyXzk5ODgiLCAiZXhwIjogMTg5MDAwMDAwMH0
    token = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VySWQiOiAidXNyXzk5ODgiLCAiZXhwIjogMTg5MDAwMDAwMH0.signature"
    uid, exp = parse_jwt_claims(token)
    assert uid == "usr_9988"
    assert exp == 1890000000

    # Malformed token
    bad_uid, bad_exp = parse_jwt_claims("bad-token")
    assert bad_uid is None
    assert bad_exp is None


def test_moviebox_session_validity():
    now = int(time.time())
    valid_sess = MovieBoxSession(token="valid_tok", expires_at=now + 3600)
    assert valid_sess.is_valid() is True

    expired_sess = MovieBoxSession(token="exp_tok", expires_at=now - 10)
    assert expired_sess.is_valid() is False

    empty_sess = MovieBoxSession(token="", expires_at=now + 3600)
    assert empty_sess.is_valid() is False


@pytest.mark.asyncio
async def test_moviebox_portal_search_parsing():
    portal = MovieBoxPortal()
    mock_response = {
        "list": [
            {
                "subjectId": "mb_101",
                "title": "Interstellar",
                "releaseYear": "2014",
                "rating": "8.7",
                "cover": "https://img.example.com/interstellar.jpg",
                "isSeries": False,
            }
        ]
    }

    with patch.object(portal, "_request_with_failover", new=AsyncMock(return_value=mock_response)):
        results = await portal.search("Interstellar")
        assert len(results) == 1
        item = results[0]
        assert "Interstellar (2014)" in item.title
        assert item.url == "moviebox://mb_101"
        assert item.year == "2014"
        assert item.rating == "8.7"
        assert item.portal_id == "moviebox"


@pytest.mark.asyncio
async def test_moviebox_portal_resolve_streams():
    portal = MovieBoxPortal()
    mock_stream_data = {
        "data": {
            "streams": [
                {
                    "url": "https://cdn.example.com/stream.m3u8",
                    "quality": "1080p",
                    "resolution": "1920x1080",
                },
                {
                    "url": "https://cdn.example.com/stream.mp4",
                    "quality": "720p",
                    "resolution": "1280x720",
                },
            ]
        }
    }

    with patch.object(portal, "_request_with_failover", new=AsyncMock(return_value=mock_stream_data)):
        streams = await portal.resolve_streams("moviebox://mb_101", season=1, episode=1)
        assert len(streams) == 2
        assert streams[0].format == "hls"
        assert streams[0].quality == "1080p"
        assert streams[1].format == "mp4"
        assert streams[1].quality == "720p"
