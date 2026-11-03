import pytest
import asyncio
from ripper.anystream import sanitize_user_url, is_valid_video_stream, extract_any_streams
from ripper.proxy_engine import get_proxied_stream_url, is_proxy_alive, ensure_proxy_running

def test_sanitize_user_url():
    # Test messy prefixes
    raw1 = "thisinput link is https://leakdom.com/15700/test/"
    assert sanitize_user_url(raw1) == "https://leakdom.com/15700/test/"

    # Test trailing punctuation & quotes
    raw2 = ' "https://d000d.com/e/f1jy0udr99xa", '
    assert sanitize_user_url(raw2) == "https://d000d.com/e/f1jy0udr99xa"

    # Test clean url
    raw3 = "https://example.com/video.mp4"
    assert sanitize_user_url(raw3) == "https://example.com/video.mp4"

    # Empty
    assert sanitize_user_url("") == ""

def test_is_valid_video_stream():
    assert is_valid_video_stream("https://cdn.example.com/movie.mp4") is True
    assert is_valid_video_stream("https://cdn.example.com/stream/master.m3u8") is True
    assert is_valid_video_stream("https://cdn.example.com/hls/master.txt") is True
    assert is_valid_video_stream("https://google-analytics.com/collect") is False
    assert is_valid_video_stream("https://cdn.example.com/thumb.jpg") is False

@pytest.mark.anyio
async def test_direct_video_extension_extraction():
    url = "https://example.com/videos/sample_1080p.mp4"
    streams = await extract_any_streams(url)
    assert len(streams) == 1
    assert streams[0]["url"] == url
    assert streams[0]["type"] == "Direct Video Link"
    assert streams[0]["confidence"] == 100

def test_proxy_engine_integration():
    ensure_proxy_running()
    assert is_proxy_alive() is True
    prox_url = get_proxied_stream_url("https://cdn.example.com/video.mp4", "https://example.com/")
    assert "127.0.0.1:5055" in prox_url
    assert "stream.mp4" in prox_url
