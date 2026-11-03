"""
Thread-safe LRU Cache with TTL partitioning for unshorten-cli.
Partitions:
- 'resolution': Resolved unshorten URLs and direct cloud endpoints (TTL: 900s)
- 'search': Multi-site search query results (TTL: 3600s)
- 'domain': Active domain radar mirrors (TTL: 86400s)
- 'circuit': Dead domain failure counts & backoffs (TTL: 300s)
"""

import time
import threading
from typing import Dict, Any, Optional
from collections import OrderedDict


class CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float):
        self.value = value
        self.expires_at = expires_at

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at


class AsyncLRUCache:
    def __init__(self, max_size: int = 512, default_ttl: float = 300.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._namespaces: Dict[str, OrderedDict[str, CacheEntry]] = {
            "resolution": OrderedDict(),
            "search": OrderedDict(),
            "domain": OrderedDict(),
            "circuit": OrderedDict(),
        }
        self._default_ttls: Dict[str, float] = {
            "resolution": 900.0,
            "search": 3600.0,
            "domain": 86400.0,
            "circuit": 300.0,
        }
        self._lock = threading.RLock()

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        """Retrieve unexpired value from namespace."""
        with self._lock:
            store = self._namespaces.get(namespace)
            if store is None or key not in store:
                return None

            entry = store[key]
            now = time.time()
            if entry.is_expired(now):
                del store[key]
                return None

            store.move_to_end(key)
            return entry.value

    async def set(self, namespace: str, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Store value with specific TTL."""
        now = time.time()
        with self._lock:
            if namespace not in self._namespaces:
                self._namespaces[namespace] = OrderedDict()
            
            ns = self._namespaces[namespace]
            effective_ttl = ttl if ttl is not None else self._default_ttls.get(namespace, self.default_ttl)
            expires_at = now + effective_ttl

            if key in ns:
                del ns[key]
            elif len(ns) >= self.max_size:
                ns.popitem(last=False)

            ns[key] = CacheEntry(value, expires_at)

    async def invalidate(self, namespace: str, key: str) -> None:
        """Remove specific key from namespace."""
        with self._lock:
            ns = self._namespaces.get(namespace)
            if ns and key in ns:
                del ns[key]

    async def clear(self, namespace: Optional[str] = None) -> None:
        """Clear specific namespace or all namespaces."""
        with self._lock:
            if namespace and namespace in self._namespaces:
                self._namespaces[namespace].clear()
            else:
                for ns in self._namespaces.values():
                    ns.clear()


GLOBAL_CACHE = AsyncLRUCache()
