"""Pure-HTTP Google reCAPTCHA v3 anchor and reload token negotiator.

Handles invisible reCAPTCHA v3 challenges without requiring external browser
automation or third-party paid solving services. Communicates directly with
Google's /anchor and /reload endpoints.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger(__name__)

RECAPTCHA_TOKEN_PATTERN = re.compile(
    r'id=["\']recaptcha-token["\']\s+value=["\']([^"\']+)["\']|"recaptcha-token"\s+value=["\']([^"\']+)["\']'
)
RRESP_PATTERN = re.compile(r'"rresp","([^"]+)"')


async def solve_recaptcha_v3_anchor(
    anchor_url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 10.0,
) -> Optional[str]:
    """Negotiate a reCAPTCHA v3 token using pure HTTP anchor/reload requests.

    Args:
        anchor_url: Full Google reCAPTCHA anchor URL containing k, co, v params.
        client: Optional existing httpx.AsyncClient instance.
        timeout: Request timeout in seconds.

    Returns:
        The valid rresp verification token if successful, or None on failure.
    """
    if not anchor_url or "recaptcha" not in anchor_url:
        logger.debug("Invalid anchor URL supplied to reCAPTCHA v3 solver: %s", anchor_url)
        return None

    parsed = urlparse(anchor_url)
    qs = parse_qs(parsed.query)

    k_val = qs.get("k", [""])[0]
    v_val = qs.get("v", [""])[0]
    co_val = qs.get("co", [""])[0]

    if not k_val:
        logger.debug("Missing sitekey 'k' parameter in anchor URL: %s", anchor_url)
        return None

    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit('/', 1)[0]}/"
    anchor_endpoint = f"{base_url}anchor"
    reload_endpoint = f"{base_url}reload?k={k_val}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    should_close = False
    if client is None:
        client = httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True)
        should_close = True

    try:
        # Step 1: Query anchor to extract initial recaptcha-token
        anchor_resp = await client.get(anchor_url, headers=headers)
        if anchor_resp.status_code != 200:
            logger.debug("reCAPTCHA anchor request failed with status: %d", anchor_resp.status_code)
            return None

        match = RECAPTCHA_TOKEN_PATTERN.search(anchor_resp.text)
        if not match:
            logger.debug("Could not locate recaptcha-token in anchor response")
            return None

        recaptcha_token = match.group(1) or match.group(2)
        if not recaptcha_token:
            return None

        # Step 2: Query reload to obtain the rresp token
        payload = f"v={v_val}&reason=q&c={recaptcha_token}&k={k_val}&co={co_val}"
        reload_resp = await client.post(reload_endpoint, data=payload, headers=headers)
        if reload_resp.status_code != 200:
            logger.debug("reCAPTCHA reload request failed with status: %d", reload_resp.status_code)
            return None

        rresp_match = RRESP_PATTERN.search(reload_resp.text)
        if not rresp_match:
            logger.debug("Could not locate rresp in reload response")
            return None

        return rresp_match.group(1)

    except Exception as exc:
        logger.debug("reCAPTCHA v3 anchor handshake failed: %s", exc)
        return None
    finally:
        if should_close:
            await client.aclose()


def solve_recaptcha_v3_anchor_sync(
    anchor_url: str,
    timeout: float = 10.0,
) -> Optional[str]:
    """Synchronous wrapper for solve_recaptcha_v3_anchor."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(
                lambda: asyncio.run(solve_recaptcha_v3_anchor(anchor_url, timeout=timeout))
            ).result()
    return asyncio.run(solve_recaptcha_v3_anchor(anchor_url, timeout=timeout))
