"""
Unit tests for AsyncLRUCache (TTL and namespace support).
"""

import asyncio
import unittest
from ripper.cache import AsyncLRUCache


class TestAsyncLRUCache(unittest.IsolatedAsyncioTestCase):
    async def test_cache_set_get_hit(self):
        cache = AsyncLRUCache(max_size=10, default_ttl=5.0)
        await cache.set("test_ns", "key1", {"data": 123})
        res = await cache.get("test_ns", "key1")
        self.assertIsNotNone(res)
        self.assertEqual(res["data"], 123)

    async def test_cache_miss(self):
        cache = AsyncLRUCache(max_size=10, default_ttl=5.0)
        res = await cache.get("test_ns", "non_existent")
        self.assertIsNone(res)

    async def test_cache_namespace_isolation(self):
        cache = AsyncLRUCache(max_size=10, default_ttl=5.0)
        await cache.set("ns1", "shared_key", "value1")
        await cache.set("ns2", "shared_key", "value2")

        self.assertEqual(await cache.get("ns1", "shared_key"), "value1")
        self.assertEqual(await cache.get("ns2", "shared_key"), "value2")

    async def test_cache_invalidation(self):
        cache = AsyncLRUCache(max_size=10, default_ttl=5.0)
        await cache.set("ns", "k", "v")
        self.assertEqual(await cache.get("ns", "k"), "v")
        await cache.invalidate("ns", "k")
        self.assertIsNone(await cache.get("ns", "k"))

    async def test_cache_ttl_expiration(self):
        cache = AsyncLRUCache(max_size=10, default_ttl=0.1)
        await cache.set("ns", "quick", "val", ttl=0.1)
        self.assertEqual(await cache.get("ns", "quick"), "val")
        await asyncio.sleep(0.15)
        self.assertIsNone(await cache.get("ns", "quick"))
