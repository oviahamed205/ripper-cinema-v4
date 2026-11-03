"""
SITE FINGERPRINTER: Auto-detects site structure, search endpoints, and download patterns.
Generates scraper configuration without any hardcoded site-specific code.
"""
import re
import asyncio
from typing import Dict, Optional, List
import httpx
from bs4 import BeautifulSoup


async def fingerprint_site(client: httpx.AsyncClient, url: str) -> Dict:
    """Auto-detect everything about a site's structure."""
    fingerprint = {
        "is_wordpress": False,
        "is_blogger": False,
        "search_type": "unknown",  # wordpress_query, api_json, form_post, url_param
        "search_endpoint": "",
        "has_sitemap": False,
        "sitemap_url": "",
        "has_rss": False,
        "rss_url": "",
        "has_cloudflare": False,
        "has_ddos_guard": False,
        "download_link_pattern": "",  # regex pattern for download links
        "movie_container_class": "",  # CSS class of movie post containers
        "pagination_type": "unknown",  # page_number, load_more, infinite_scroll
    }

    try:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8.0)
        html = resp.text
        headers = dict(resp.headers)

        # Server detection
        server = headers.get("server", "").lower()
        if "cloudflare" in server:
            fingerprint["has_cloudflare"] = True
        if "ddos-guard" in server:
            fingerprint["has_ddos_guard"] = True

        # WordPress detection
        wp_signals = ["wp-content", "wp-includes", "wp-json", "wordpress"]
        fingerprint["is_wordpress"] = any(s in html for s in wp_signals)

        if fingerprint["is_wordpress"]:
            fingerprint["search_type"] = "wordpress_query"
            fingerprint["search_endpoint"] = f"{url.rstrip('/')}/?s={{query}}"
            fingerprint["sitemap_url"] = f"{url.rstrip('/')}/wp-sitemap.xml"
            fingerprint["rss_url"] = f"{url.rstrip('/')}/feed/"

        # Blogger detection
        if "blogspot" in url or "blogger" in html:
            fingerprint["is_blogger"] = True
            fingerprint["search_type"] = "url_param"
            fingerprint["search_endpoint"] = f"{url.rstrip('/')}/search?q={{query}}"

        # Check sitemap exists
        if fingerprint["sitemap_url"]:
            try:
                sm_resp = await client.head(fingerprint["sitemap_url"], timeout=3.0)
                fingerprint["has_sitemap"] = sm_resp.status_code == 200
            except Exception:
                pass

        # Check RSS exists
        if fingerprint["rss_url"]:
            try:
                rss_resp = await client.head(fingerprint["rss_url"], timeout=3.0)
                fingerprint["has_rss"] = rss_resp.status_code == 200
            except Exception:
                pass

        # Detect download link patterns
        soup = BeautifulSoup(html, "html.parser")
        download_links = soup.find_all("a", href=re.compile(r"download|server|mirror|drive|cloud|r2|s3", re.I))
        if download_links:
            # Find common class patterns
            classes = set()
            for a in download_links:
                for c in a.get("class", []):
                    classes.add(c)
            if classes:
                fingerprint["movie_container_class"] = " ".join(list(classes)[:3])

        # Detect pagination
        if "/page/2" in html or "paged=2" in html:
            fingerprint["pagination_type"] = "page_number"
        elif "load more" in html.lower():
            fingerprint["pagination_type"] = "load_more"

    except Exception:
        pass

    return fingerprint
