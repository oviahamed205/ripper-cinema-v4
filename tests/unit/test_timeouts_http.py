"""
Unit tests for http connection pool singleton and timeouts.
"""

import unittest
from ripper.timeouts import build_timeout, TimeoutCascade
from ripper.http_client import get_shared_client, close_shared_client


class TestTimeoutsHttp(unittest.IsolatedAsyncioTestCase):
    def test_build_timeout(self):
        t = build_timeout(5.0)
        self.assertAlmostEqual(t.connect, 1.5)
        self.assertAlmostEqual(t.read, 3.5)

    async def test_shared_client_singleton(self):
        c1 = await get_shared_client()
        c2 = await get_shared_client()
        self.assertIs(c1, c2)
        await close_shared_client()
