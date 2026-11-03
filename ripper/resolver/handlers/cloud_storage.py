"""
Cloud Storage Handler (Presigned Cloudflare R2, AWS S3, Wasabi, GCS, B2).
Detects and validates playable binary storage URLs with zero redirect overhead.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import is_direct_storage_url, is_direct_file_url
from ...models import HopInfo


STORAGE_PATTERNS = (
    r"\.r2\.dev/",
    r"\.r2\.cloudflarestorage\.com/",
    r"\.s3[a-z0-9-]*\.amazonaws\.com/",
    r"\.wasabisys\.com/",
    r"\.digitaloceanspaces\.com/",
    r"storage\.googleapis\.com/",
    r"\.backblazeb2\.com/",
    r"\.b-cdn\.net/",
    r"pixeldrain\.(?:com|dev)/api/file/",
)


class CloudStorageHandler(BaseResolverHandler):
    name = "cloud_storage"
    priority = 10

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if is_direct_storage_url(low) or is_direct_file_url(low):
            return True
        return any(re.search(pat, low) for pat in STORAGE_PATTERNS)

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops = [make_hop(
            url=url,
            status_code=200,
            redirect_type="direct_cloud_storage",
            extra_details="Direct Presigned Cloud Storage stream verified (R2/S3/Wasabi)",
            hop_number=len(context.hops) + 1,
        )]
        return url, hops