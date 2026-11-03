"""
Smart Pause-Ahead Stream Buffer & HTTP 206 Reverse Proxy
Features:
- Full HTTP 206 Partial Content Range Requests for seamless seeking/scrubbing
- 30-Minute Aggressive Pre-Buffer on Pause (Zero-Buffer Playback Resume)
- Anti-Hotlink Header Injection (Referer, User-Agent, Range)
"""

import os
import sys
import time
import asyncio
import threading
import httpx
from typing import Dict, Optional, Tuple

# In-memory stream buffer cache: stream_id -> StreamBufferSession
STREAM_SESSIONS: Dict[str, "StreamBufferSession"] = {}

class StreamBufferSession:
    def __init__(self, stream_id: str, target_url: str, headers: Dict[str, str]):
        self.stream_id = stream_id
        self.target_url = target_url
        self.headers = headers
        self.total_size = 0
        self.content_type = "video/mp4"
        self.is_paused = False
        self.buffer_task: Optional[asyncio.Task] = None
        self.buffered_chunks: Dict[int, bytes] = {} # chunk_index -> bytes (64KB chunks)
        self.current_play_byte = 0
        self.max_ahead_bytes = 250 * 1024 * 1024 # ~250 MB (approx 30 mins for 1080p stream)

    async def init_metadata(self):
        async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
            try:
                head_resp = await client.head(self.target_url, headers=self.headers)
                self.total_size = int(head_resp.headers.get("content-length", 0))
                self.content_type = head_resp.headers.get("content-type", "video/mp4")
            except Exception:
                pass

    def on_user_pause(self, current_byte_pos: int):
        """Trigger aggressive 30-minute forward buffer when user pauses."""
        self.is_paused = True
        self.current_play_byte = current_byte_pos
        # Start background pre-buffering task
        try:
            loop = asyncio.get_event_loop()
            if self.buffer_task and not self.buffer_task.done():
                self.buffer_task.cancel()
            self.buffer_task = loop.create_task(self._pre_buffer_worker())
        except Exception:
            pass

    def on_user_resume(self):
        """User resumes playback."""
        self.is_paused = False

    async def _pre_buffer_worker(self):
        """Aggressively buffers up to 30 mins (~250MB) ahead in chunks."""
        start_byte = self.current_play_byte
        end_byte = min(start_byte + self.max_ahead_bytes, self.total_size if self.total_size > 0 else start_byte + self.max_ahead_bytes)
        
        chunk_size = 128 * 1024 # 128 KB
        curr = start_byte

        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            while curr < end_byte and self.is_paused:
                chunk_end = min(curr + chunk_size - 1, end_byte - 1)
                req_headers = dict(self.headers)
                req_headers["Range"] = f"bytes={curr}-{chunk_end}"
                try:
                    res = await client.get(self.target_url, headers=req_headers)
                    if res.status_code in [200, 206]:
                        chunk_idx = curr // chunk_size
                        self.buffered_chunks[chunk_idx] = res.content
                        curr = chunk_end + 1
                    else:
                        break
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(1)


def register_stream_session(stream_id: str, target_url: str, referer: str = "") -> StreamBufferSession:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer
    else:
        headers["Referer"] = target_url

    session = StreamBufferSession(stream_id, target_url, headers)
    STREAM_SESSIONS[stream_id] = session
    return session
