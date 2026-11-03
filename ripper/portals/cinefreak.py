"""
CineFreak Portal Resolver for Ripper.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
import httpx

from .base import BasePortal, PortalStreamResult


class CineFreakPortal(BasePortal):
    portal_name = "CineFreak"
    supported_domains = ["cinefreak.net", "cinefreak.org"]

    async def search(self, query: str) -> List[Dict[str, Any]]:
        results = []
        search_url = f"https://cinefreak.net/?s={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
                resp = await client.get(search_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for article in soup.find_all("article"):
                        a = article.find("a", href=True)
                        if a:
                            title = a.get_text(strip=True) or (article.find("h2") and article.find("h2").get_text(strip=True))
                            if title and a["href"]:
                                results.append({
                                    "title": title,
                                    "url": a["href"],
                                    "source": self.portal_name,
                                })
        except Exception:
            pass
        return results

    async def extract_streams(self, page_url: str) -> List[PortalStreamResult]:
        return []