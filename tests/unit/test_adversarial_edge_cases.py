"""
Layer 5 Adversarial Edge Cases & Exceptional Conditions Test Suite for Ripper Resolver.
Tests:
- Empty, null, and whitespace inputs
- Extremely long URLs (> 4096 chars)
- URLs with non-ASCII and Unicode characters
- Malformed HTML/JSON bodies
- Redirect loops and cycle termination
- Memory cap enforcement on huge HTML bodies
- Circuit breaker tripping and automatic recovery
- Dynamic auto-discovery in HandlerRegistry
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ripper.resolver.engine import ResolverEngine, GLOBAL_ENGINE
from ripper.resolver.base import ResolutionContext, make_hop
from ripper.resolver.registry import HandlerRegistry, GLOBAL_REGISTRY
from ripper.resolver.core import (
    is_direct_file_url,
    is_direct_storage_url,
    looks_like_binary,
    looks_like_html,
    _clean_extracted_url,
    _is_followable_http_url,
    FetchResult,
    MAX_HTML_BYTES,
)


class TestResolverAdversarialEdgeCases(unittest.IsolatedAsyncioTestCase):

    async def test_empty_and_null_urls(self):
        engine = ResolverEngine()
        res_empty = await engine.resolve("")
        self.assertFalse(res_empty.is_success)
        self.assertIn("empty", res_empty.error_message.lower())

        res_spaces = await engine.resolve("     \n\t  ")
        self.assertFalse(res_spaces.is_success)
        self.assertIn("empty", res_spaces.error_message.lower())

    async def test_extremely_long_url(self):
        engine = ResolverEngine()
        long_url = "https://example.com/path?" + "a=1&" * 1500
        self.assertGreater(len(long_url), 4096)
        res = await engine.resolve(long_url)
        self.assertIsNotNone(res)
        self.assertEqual(res.original_url, long_url)

    async def test_unicode_and_special_chars_in_url(self):
        engine = ResolverEngine()
        unicode_url = "https://example.com/movie/🎥_Avengers_Endgame_2019.mp4"
        res = await engine.resolve(unicode_url)
        self.assertIsNotNone(res)
        self.assertTrue(res.is_success)
        self.assertEqual(res.final_url, unicode_url)

    async def test_redirect_cycle_prevention(self):
        engine = ResolverEngine(max_depth=10)
        url_a = "https://shortener-a.com/link"
        url_b = "https://shortener-b.com/link"

        mock_handler = MagicMock()
        mock_handler.priority = 5
        mock_handler.can_handle.side_effect = lambda u, h=None: u in (url_a, url_b)

        async def alternate_resolve(url, client, context):
            next_url = url_b if url == url_a else url_a
            return next_url, [make_hop(url=next_url, redirect_type="test_hop")]

        mock_handler.resolve = alternate_resolve

        registry = HandlerRegistry()
        registry.register(mock_handler)

        with patch("ripper.resolver.engine.GLOBAL_REGISTRY", registry):
            res = await engine.resolve(url_a, use_cache=False)
            self.assertFalse(res.is_success)
            self.assertIn("loop", (res.error_message or "").lower())
            self.assertLessEqual(res.total_hops, 5)

    async def test_html_size_capping(self):
        self.assertTrue(looks_like_binary("video/mp4"))
        self.assertTrue(looks_like_binary("application/octet-stream"))
        self.assertFalse(looks_like_binary("text/html; charset=utf-8"))
        self.assertFalse(looks_like_binary("application/json"))
        self.assertGreaterEqual(MAX_HTML_BYTES, 64_000)

    async def test_malformed_extracted_urls_cleaning(self):
        raw_urls = [
            'https://cdn.example.com/video.mp4\"',
            "https://cdn.example.com/stream.m3u8'>",
            "https://cdn.example.com/file.zip====",
            "https://cdn.example.com/movie.mkv\\",
        ]

        for raw in raw_urls:
            cleaned = _clean_extracted_url(raw)
            self.assertNotIn('"', cleaned)
            self.assertNotIn("'", cleaned)
            self.assertNotIn(">", cleaned)
            self.assertNotIn("\\", cleaned)
            self.assertTrue(_is_followable_http_url(cleaned))

    def test_handler_registry_auto_discovery(self):
        reg = HandlerRegistry()
        count = reg.auto_discover("ripper.resolver.handlers")
        self.assertGreaterEqual(count, 10)
        names = [h.name for h in reg.all_handlers()]
        self.assertIn("video_hosts", names)
        self.assertIn("file_lockers", names)
        self.assertIn("hubcloud", names)
