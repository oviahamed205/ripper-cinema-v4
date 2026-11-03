"""
DLC (Download Link Container) Parser & Decryptor.
Decodes .dlc container files and extracts enclosed media and file links.
"""

from __future__ import annotations

import base64
import re
import time
from typing import List, Optional

import httpx

from ripper.universal_bypasser.containers.base import BaseContainerUnroller
from ripper.universal_bypasser.models import ContainerResult, GateType


class DLCDecoder(BaseContainerUnroller):
    """Parses and unrolls encrypted .dlc container files."""

    name: str = "dlc_decoder"

    async def unroll(self, url: str) -> ContainerResult:
        start_time = time.time()
        unlocked: List[str] = []

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ContainerResult(
                        container_url=url,
                        gate_type=GateType.CONTAINER,
                        success=False,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        error=f"Failed to fetch DLC file: HTTP {resp.status_code}"
                    )

                content = resp.content

                # If the DLC file is base64 encoded text or raw binary:
                dlc_text = ""
                try:
                    dlc_text = content.decode("utf-8")
                except Exception:
                    dlc_text = base64.b64encode(content).decode("ascii")

                # Strategy 1: dcrypt.it REST API unrolling
                try:
                    dcrypt_url = "http://dcrypt.it/decrypt/paste"
                    api_resp = await client.post(dcrypt_url, data={"content": dlc_text}, timeout=10.0)
                    if api_resp.status_code == 200:
                        data = api_resp.json()
                        # dcrypt returns {"success": {"links": [...]}}
                        if "success" in data and "links" in data["success"]:
                            for link in data["success"]["links"]:
                                if link not in unlocked:
                                    unlocked.append(link)
                except Exception:
                    pass

                # Strategy 2: Direct regex inspection for any unencrypted URLs embedded in container
                if not unlocked:
                    raw_urls = re.findall(r'https?://[a-zA-Z0-9\.\-_/]+', dlc_text)
                    for u in raw_urls:
                        if not u.endswith((".dtd", ".xsd", ".xml")) and "w3.org" not in u:
                            if u not in unlocked:
                                unlocked.append(u)

                return ContainerResult(
                    container_url=url,
                    title="DLC Package Container",
                    gate_type=GateType.CONTAINER,
                    unlocked_urls=unlocked,
                    total_links=len(unlocked),
                    success=len(unlocked) > 0,
                    duration=time.time() - start_time,
                    solver_used=self.name
                )

        except Exception as e:
            return ContainerResult(
                container_url=url,
                gate_type=GateType.CONTAINER,
                success=False,
                duration=time.time() - start_time,
                solver_used=self.name,
                error=str(e)
            )
