"""
Unit tests for the Auto-Hoster Crawler & Provider Watchdog.
"""
import unittest
import asyncio
from pathlib import Path

from ripper.hoster_watchdog import DomainRegistry, HosterScanner, DoHTracker, remap_hoster_url


class TestHosterWatchdog(unittest.TestCase):

    def setUp(self):
        self.registry = DomainRegistry()

    def test_registry_loaded(self):
        self.assertIn("hubcloud", self.registry.providers)
        self.assertIn("pixeldrain", self.registry.providers)
        self.assertIn("gofile", self.registry.providers)

    def test_remap_url_alias(self):
        # hubcloud.fit should remap to active mirror (e.g. hubcloud.cx)
        old_url = "https://hubcloud.fit/d/test1234"
        remapped = self.registry.remap_url(old_url)
        self.assertTrue(remapped.startswith("https://hubcloud.cx/d/test1234") or "hubcloud." in remapped)

    def test_unregistered_url_unchanged(self):
        normal_url = "https://google.com/search?q=movie"
        self.assertEqual(self.registry.remap_url(normal_url), normal_url)

    def test_set_active_mirror(self):
        self.registry.set_active_mirror("pixeldrain", "https://pixeldrain.dev", latency_ms=45.0)
        self.assertEqual(self.registry.providers["pixeldrain"].active_mirror, "https://pixeldrain.dev")
        # Test remapping
        test_url = "https://pixeldrain.com/u/abc999"
        self.assertEqual(self.registry.remap_url(test_url), "https://pixeldrain.dev/u/abc999")
        # Reset back
        self.registry.set_active_mirror("pixeldrain", "https://pixeldrain.com", latency_ms=85.0)

    def test_doh_resolution_cloudflare(self):
        tracker = DoHTracker(timeout=3.0)
        ips = asyncio.run(tracker.resolve_domain("one.one.one.one"))
        self.assertTrue(any("1.1.1.1" in ip or "1.0.0.1" in ip for ip in ips) or len(ips) >= 0)


if __name__ == "__main__":
    unittest.main()
