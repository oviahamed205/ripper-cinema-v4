"""
Unit tests for domains module, disk persistence, and radar.
"""

import unittest
from ripper.domains import get_active_domain, DEFAULT_SITE_DOMAINS


class TestDomains(unittest.IsolatedAsyncioTestCase):
    async def test_get_active_domain_defaults(self):
        cine_url = await get_active_domain("cinefreak")
        self.assertTrue(cine_url.startswith("https://"))
        self.assertIn("cinefreak", cine_url)

        vega_url = await get_active_domain("vegamovies")
        self.assertTrue(vega_url.startswith("https://"))
        self.assertIn("vegamovies", vega_url)

    async def test_fallback_domain(self):
        unknown_url = await get_active_domain("unknownsite")
        self.assertEqual(unknown_url, "https://unknownsite.com")
