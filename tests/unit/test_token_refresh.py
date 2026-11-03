import unittest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import httpx

from ripper.downloader.engine import TokenRefreshCoordinator, download_chunk_worker


class TestTokenRefresh(unittest.TestCase):

    def test_token_refresh_coordinator_reactive_refresh(self):
        async def _run():
            call_count = 0

            async def mock_refresh():
                nonlocal call_count
                call_count += 1
                return f"https://pub-abc.r2.dev/video.mkv?token=fresh_{call_count}"

            coord = TokenRefreshCoordinator("https://pub-abc.r2.dev/video.mkv?token=expired", refresh_func=mock_refresh)

            initial_url = await coord.get_url()
            self.assertIn("token=expired", initial_url)

            new_url = await coord.request_fresh_url(caller_idx=0)
            self.assertIn("token=fresh_1", new_url)
            self.assertEqual(call_count, 1)

            second_url = await coord.request_fresh_url(caller_idx=1)
            self.assertEqual(second_url, new_url)
            self.assertEqual(call_count, 1)

        asyncio.run(_run())

    def test_download_chunk_worker_recovers_from_403(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            part_file = Path(td) / "test.part0"

            async def _run():
                refresh_called = False

                async def mock_refresh():
                    nonlocal refresh_called
                    refresh_called = True
                    return "https://valid.r2.dev/video.mkv"

                coord = TokenRefreshCoordinator("https://expired.r2.dev/video.mkv", refresh_func=mock_refresh)

                progress = MagicMock()
                state = {"chunks": [{"downloaded": 0, "done": False}]}

                client = AsyncMock(spec=httpx.AsyncClient)

                class MockStreamContext:
                    def __init__(self, status_code, content):
                        self.status_code = status_code
                        self._content = content

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, exc_type, exc_val, exc_tb):
                        pass

                    async def aiter_bytes(self, chunk_size=64 * 1024):
                        yield self._content

                def stream_side_effect(method, url, headers=None):
                    if "expired.r2.dev" in url:
                        return MockStreamContext(403, b"")
                    return MockStreamContext(206, b"SAMPLE_VIDEO_BYTES")

                client.stream.side_effect = stream_side_effect

                await download_chunk_worker(
                    client=client,
                    coordinator=coord,
                    headers={},
                    start_byte=0,
                    end_byte=17,
                    part_file=part_file,
                    progress=progress,
                    task_id=1,
                    state=state,
                    chunk_idx=0,
                    max_retries=3
                )

                self.assertTrue(refresh_called)
                self.assertTrue(part_file.exists())
                self.assertEqual(part_file.read_bytes(), b"SAMPLE_VIDEO_BYTES")
                self.assertTrue(state["chunks"][0]["done"])

            asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
