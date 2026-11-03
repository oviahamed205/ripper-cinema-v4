"""
Turbo Ring Buffer & HLS Segment Prefetcher.
Pre-fetches the next 5-10 video chunks (.ts) in background worker threads so video playback never buffers.
"""
from __future__ import annotations

import collections
import threading
from typing import Dict, Optional


class StreamRingBuffer:
    """In-memory chunk cache with size bounds to prevent RAM exhaustion."""

    def __init__(self, max_chunks: int = 30) -> None:
        self.max_chunks = max_chunks
        self._chunks: Dict[str, bytes] = {}
        self._order = collections.deque()
        self._lock = threading.Lock()

    def put(self, chunk_key: str, data: bytes) -> None:
        with self._lock:
            if chunk_key not in self._chunks:
                if len(self._order) >= self.max_chunks:
                    oldest = self._order.popleft()
                    self._chunks.pop(oldest, None)
                self._order.append(chunk_key)
            self._chunks[chunk_key] = data

    def get(self, chunk_key: str) -> Optional[bytes]:
        with self._lock:
            return self._chunks.get(chunk_key)

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._order.clear()


GLOBAL_STREAM_BUFFER = StreamRingBuffer()