"""
AUTO-SCRAPER: Generates search and extraction functions for any site
based on its fingerprint. No hardcoded site-specific code needed.
"""
import re
import urllib.parse
from typing import List, Dict
import httpx
from bs4 import BeautifulSoup


async def auto_search_site(client: httpx.AsyncClient, site_url: str, query: str, fingerprint: Dict) -> List[Dict]:
    """Universal search function that adapts to any site structure."""
    results = []

    try:
        # Build search URL based on fingerprint
        if fingerprint.get("search_type") == "wordpress_query":
            search_url = f"{site_url.rstrip('/')}/?s={urllib.parse.quote_plus(query)}"
        elif fingerprint.get("search_type") == "url_param":
            search_url = f"{site_url.rstrip('/')}/search?q={urllib.parse.quote_plus(query)}"
        elif fingerprint.get("search_type") == "api_json":
            endpoint = fingerprint.get("search_endpoint", f"{site_url}/?s={{query}}")
            search_url = endpoint.replace("{query}", urllib.parse.quote_plus(query))
        else:
            search_url = f"{site_url.rstrip('/')}/?s={urllib.parse.quote_plus(query)}"

        resp = await client.get(search_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=6.0)

        if resp.status_code != 200:
            return results

        # Handle JSON API responses
        if fingerprint.get("search_type") == "api_json":
            data = resp.json()
            hits = data.get("hits", data.get("results", data.get("posts", [])))
            for hit in hits:
                if isinstance(hit, dict):
                    title = hit.get("post_title", hit.get("title", ""))
                    link = hit.get("permalink", hit.get("link", hit.get("url", "")))
                    if title and link:
                        results.append({"title": title, "url": link, "site": site_url})
            return results

        # Handle HTML responses
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to find movie post containers
        containers = []
        if fingerprint.get("movie_container_class"):
            containers = soup.find_all(class_=re.compile(fingerprint["movie_container_class"], re.I))

        if not containers:
            domain = urllib.parse.urlparse(site_url).netloc
            for a in soup.find_all("a", href=True):
                title = a.get_text().strip()
                href = a["href"]
                if title and len(title) > 5 and domain in href:
                    if not any(skip in href for skip in ["/category/", "/page/", "/tag/", "/author/", "/privacy", "/contact"]):
                        results.append({"title": title, "url": href, "site": site_url})

        return results

    except Exception:
        return results
