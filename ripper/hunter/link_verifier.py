"""
LINK VERIFIER: Validates download/stream URLs before presenting to user.
Sends HEAD request, checks status, content-type, file size.
"""
import asyncio
from dataclasses import dataclass
from typing import Optional
import httpx


@dataclass
class LinkVerificationResult:
    url: str
    is_valid: bool
    status_code: int = 0
    content_type: str = ""
    content_length: int = 0
    is_direct_stream: bool = False
    error: str = ""


async def verify_link(client: httpx.AsyncClient, url: str, timeout: float = 4.0) -> LinkVerificationResult:
    """Send HEAD request to verify a link is alive and get metadata."""
    try:
        resp = await client.head(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout, follow_redirects=True)
        is_valid = resp.status_code < 400
        ct = resp.headers.get("content-type", "")
        cl = int(resp.headers.get("content-length", 0))

        is_stream = any(x in ct for x in ["video/", "audio/", "application/octet-stream"]) or \
                    any(x in url.lower() for x in [".mkv", ".mp4", ".avi", "r2.cloudflarestorage", "amazonaws.com", "pixeldrain", "gofile"])

        return LinkVerificationResult(
            url=url,
            is_valid=is_valid,
            status_code=resp.status_code,
            content_type=ct,
            content_length=cl,
            is_direct_stream=is_stream,
        )
    except Exception as e:
        return LinkVerificationResult(url=url, is_valid=False, error=str(e))
