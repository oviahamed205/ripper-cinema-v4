"""
Filecrypt.cc Container & Folder Unroller.
Extracts and resolves all encrypted or tokenized links from Filecrypt.cc / Filecrypt.co containers.
"""

from __future__ import annotations

import asyncio
import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.containers.base import BaseContainerUnroller
from ripper.universal_bypasser.models import ContainerResult, GateType


class FilecryptUnroller(BaseContainerUnroller):
    """Unrolls Filecrypt.cc containers into individual hoster URLs."""

    name: str = "filecrypt"

    async def unroll(self, url: str) -> ContainerResult:
        start_time = time.time()
        unlocked: list[str] = []

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
                        error=f"Filecrypt returned HTTP {resp.status_code}"
                    )

                html = resp.text
                soup = BeautifulSoup(html, "html.parser")
                base_url = f"{urlparse(str(resp.url)).scheme}://{urlparse(str(resp.url)).netloc}"

                # Extract container title
                title_node = soup.find(["h2", "h3"], class_=re.compile(r"title|folder", re.I)) or soup.find("title")
                title = title_node.text.strip() if title_node else "Filecrypt Container"

                # Check for password prompt
                pwd_form = soup.find("form", id=re.compile(r"pass|container", re.I))
                if pwd_form and soup.find("input", {"type": "password"}):
                    # Attempt common container passwords or password from context if provided
                    passwords = ["", "1234", "password"]
                    if "password" in self.context.headers:
                        passwords.insert(0, self.context.headers["password"])

                    for pwd in passwords:
                        post_data = {"password": pwd}
                        for hidden in pwd_form.find_all("input", {"type": "hidden"}):
                            post_data[hidden.get("name")] = hidden.get("value", "")
                        action = urljoin(base_url, pwd_form.get("action", ""))
                        pwd_resp = await client.post(action, data=post_data)
                        if "password" not in pwd_resp.text.lower() or "openLink" in pwd_resp.text:
                            html = pwd_resp.text
                            soup = BeautifulSoup(html, "html.parser")
                            break

                # 1. Collect /Link/<token>.html links and openLink JS calls
                link_tokens: list[str] = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/Link/" in href:
                        link_tokens.append(urljoin(base_url, href))

                # Collect openLink('...') or onclick attributes
                open_link_matches = re.findall(r"openLink\(['\"]([^'\"]+)['\"]", html)
                for tok in open_link_matches:
                    target_url = urljoin(base_url, f"/Link/{tok}.html")
                    if target_url not in link_tokens:
                        link_tokens.append(target_url)

                # Collect direct hoster links if any are unmasked
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith(("http://", "https://")) and "filecrypt" not in href:
                        if not href.endswith((".css", ".js", ".png", ".jpg")):
                            if href not in unlocked:
                                unlocked.append(href)

                # 2. Concurrently resolve /Link/<token>.html tokens by following redirects
                async def resolve_token(token_url: str) -> str | None:
                    try:
                        # Use a client that doesn't follow redirects to catch Location header
                        async with self.get_client(follow_redirects=False) as no_redirect_client:
                            r = await no_redirect_client.get(token_url)
                            if r.status_code in (301, 302, 303, 307, 308) and "Location" in r.headers:
                                loc = r.headers["Location"]
                                if "filecrypt" not in loc:
                                    return loc
                            # If followed, check final text or redirect
                            if r.status_code == 200:
                                m = re.search(r'https?://[^\s"\'<>]+', r.text)
                                if m and "filecrypt" not in m.group(0):
                                    return m.group(0)
                    except Exception:
                        pass
                    return None

                if link_tokens:
                    tasks = [resolve_token(tok) for tok in link_tokens[:30]]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, str) and res.startswith("http") and res not in unlocked:
                            unlocked.append(res)

                # 3. Check for DLC container if direct links were not fully populated
                if not unlocked:
                    dlc_match = re.search(r'href=["\'](/DLC/[^"\']+)["\']', html)
                    if dlc_match:
                        dlc_url = urljoin(base_url, dlc_match.group(1))
                        unlocked.append(dlc_url)

                return ContainerResult(
                    container_url=url,
                    title=title,
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
