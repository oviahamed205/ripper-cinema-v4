"""
ripper.ripperdb.fmhy_sync
~~~~~~~~~~~~~~~~~~~~~~~~~

Live crawler & parser for https://fmhy.net/video.
Extracts active video providers, mirrors, and archetypes, populates ripperdb SQLite,
and atomically updates ripper's hoster_watchdog/domain_registry.json.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ripper.ripperdb.fmhy_sync")

FMHY_VIDEO_URL = "https://fmhy.net/video"
FMHY_GITHUB_RAW_URL = "https://raw.githubusercontent.com/fmhy/FMHYEdit/main/docs/video.md"
REGISTRY_JSON_PATH = Path(__file__).resolve().parent.parent / "hoster_watchdog" / "domain_registry.json"
SEED_FILE_PATH = Path(__file__).resolve().parent / "data" / "fmhy_video_seed.md"


@dataclass
class ParsedProvider:
    key: str
    name: str
    primary_url: str
    mirrors: List[str]
    section: str
    archetype: str = "custom"
    supports_auto_next: bool = False
    supports_4k: bool = False
    status_page: Optional[str] = None


def clean_domain(url: str) -> str:
    """Extracts clean lowercase hostname without www."""
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc or parsed.path
        netloc = netloc.split(":")[0].lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def detect_archetype(name: str, url: str, tags: str, section_title: str = "") -> str:
    """Classifies provider site into an automation archetype driver."""
    blob = f"{name} {url} {tags} {section_title}".lower()

    if "p-stream" in blob or "pstream" in blob:
        return "pstream"
    if "torrent" in blob:
        return "torrent"
    if "ddl" in blob or "download" in blob or "vegamovies" in blob:
        return "ddl"
    if any(k in blob for k in ["cinejoy", "rivestream", "flixer", "hexa", "stellar", "vidplay", "smashystream", "stream"]):
        return "embed"
    return "custom"


class FMHYRegistrySync:
    """Parses FMHY video directory markdown or fetches live from fmhy.net."""

    def __init__(self, cache_engine: Optional[Any] = None):
        if cache_engine is None:
            from ripper.ripperdb.cache import RipperDBCache
            self.cache = RipperDBCache()
        else:
            self.cache = cache_engine
        self.registry_path = REGISTRY_JSON_PATH

    def parse_markdown(self, content: str) -> List[ParsedProvider]:
        """
        Parses FMHY /video markdown structure, extracting provider names,
        primary domains, backup mirrors, and capabilities.
        """
        providers: List[ParsedProvider] = []
        current_section = "streaming"
        current_subsection = ""

        section_re = re.compile(r"^#+\s*[📂🔹►▷⭐]?\s*(.*)$")
        link_re = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")

        lines = content.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            sec_match = section_re.match(line_str)
            if sec_match:
                header = sec_match.group(1).lower()
                current_subsection = header
                if "download" in header or "ddl" in header:
                    current_section = "ddl"
                elif "torrent" in header:
                    current_section = "torrent"
                elif "anime" in header:
                    current_section = "anime"
                elif "streaming" in header or "stream" in header:
                    current_section = "streaming"
                continue

            if any(k in current_section for k in ["live tv", "sports", "iptv"]):
                continue

            if line_str.startswith(("-", "*")):
                matches = link_re.findall(line_str)
                if not matches:
                    continue

                valid_links = []
                status_url = None
                for label, link_url in matches:
                    if "rentry.co" in link_url or label.lower() == "status":
                        status_url = link_url
                    elif any(s in label.lower() for s in ["guide", "docs", "discord", "reddit", "userscript"]):
                        continue
                    else:
                        valid_links.append((label, link_url))

                if not valid_links:
                    continue

                primary_label, primary_url = valid_links[0]
                primary_name = re.sub(r"[\*\_\`]", "", primary_label).strip()

                domain_key = clean_domain(primary_url).split(".")[0]
                if not domain_key:
                    domain_key = re.sub(r"[^\w]", "_", primary_name).lower()

                all_mirrors = [primary_url]
                for label, link_url in valid_links[1:]:
                    if link_url not in all_mirrors:
                        all_mirrors.append(link_url)

                supports_auto_next = "auto-next" in line_str.lower()
                supports_4k = "4k" in line_str.lower()
                archetype = detect_archetype(primary_name, primary_url, line_str, current_subsection)

                provider = ParsedProvider(
                    key=domain_key,
                    name=primary_name,
                    primary_url=primary_url,
                    mirrors=all_mirrors,
                    section=current_section,
                    archetype=archetype,
                    supports_auto_next=supports_auto_next,
                    supports_4k=supports_4k,
                    status_page=status_url,
                )
                providers.append(provider)

        # Consolidate duplicate domain keys while merging mirrors & capabilities
        consolidated: Dict[str, ParsedProvider] = {}
        for p in providers:
            if p.key in consolidated:
                existing = consolidated[p.key]
                for m in p.mirrors:
                    if m not in existing.mirrors:
                        existing.mirrors.append(m)
                if p.supports_auto_next:
                    existing.supports_auto_next = True
                if p.supports_4k:
                    existing.supports_4k = True
                if p.status_page and not existing.status_page:
                    existing.status_page = p.status_page
            else:
                consolidated[p.key] = p

        return list(consolidated.values())

    def parse_html(self, content: str) -> List[ParsedProvider]:
        """
        Parses live HTML from https://fmhy.net/video using BeautifulSoup.
        Extracts all active video providers, mirrors, tags, capabilities,
        and status pages without missing any <li> item.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content, "html.parser")
        excluded_keywords = [
            "live tv", "sports", "iptv", "base64 encoded link", "wiki",
            "tools", "more", "tracking", "database", "calendar", "upcoming",
            "subtitle", "stremio tools", "smart tv"
        ]

        providers: List[ParsedProvider] = []
        current_section = "streaming"
        current_sub = ""

        for elem in soup.find_all(["h1", "h2", "h3", "li"]):
            if elem.name in ("h1", "h2", "h3"):
                title = elem.get_text(strip=True).lower()
                if elem.name in ("h1", "h2"):
                    current_section = title
                    current_sub = ""
                else:
                    current_sub = title
                continue

            # It's an li element
            if any(ex in current_section for ex in excluded_keywords) or any(ex in current_sub for ex in excluded_keywords):
                continue

            anchors = elem.find_all("a", href=True)
            if not anchors:
                continue

            valid_links = []
            status_url = None

            for a in anchors:
                href = a["href"].strip()
                text = a.get_text(strip=True)
                if not href.startswith(("http://", "https://")):
                    continue
                if "rentry.co" in href or text.lower() == "status":
                    status_url = href
                elif any(s in text.lower() for s in ["discord", "reddit", "userscript", "guide", "docs", "donate", "telegram", "wiki"]):
                    continue
                elif any(s in href.lower() for s in ["discord.gg", "reddit.com", "greasyfork.org", "t.me"]):
                    continue
                else:
                    valid_links.append((text, href))

            if not valid_links:
                continue

            primary_text, primary_url = valid_links[0]
            primary_name = primary_text.replace("*", "").replace("_", "").replace("`", "").strip()
            if not primary_name or primary_name.isdigit():
                primary_name = clean_domain(primary_url)

            domain_key = clean_domain(primary_url).split(".")[0]
            if not domain_key:
                domain_key = re.sub(r"[^a-zA-Z0-9]", "_", primary_name).lower()

            all_mirrors = [primary_url]
            for text, href in valid_links[1:]:
                if href not in all_mirrors:
                    all_mirrors.append(href)

            full_text = elem.get_text(" ", strip=True)
            supports_auto_next = "auto-next" in full_text.lower()
            supports_4k = "4k" in full_text.lower()

            sec = "streaming"
            if "download" in current_section or "download" in current_sub or "ddl" in current_section:
                sec = "ddl"
            elif "torrent" in current_section or "torrent" in current_sub:
                sec = "torrent"
            elif "anime" in current_section or "anime" in current_sub:
                sec = "anime"

            archetype = detect_archetype(primary_name, primary_url, full_text, current_sub)

            providers.append(
                ParsedProvider(
                    key=domain_key,
                    name=primary_name,
                    primary_url=primary_url,
                    mirrors=all_mirrors,
                    section=sec,
                    archetype=archetype,
                    supports_auto_next=supports_auto_next,
                    supports_4k=supports_4k,
                    status_page=status_url,
                )
            )

        # Consolidate duplicate keys
        consolidated: Dict[str, ParsedProvider] = {}
        for p in providers:
            if p.key in consolidated:
                existing = consolidated[p.key]
                for m in p.mirrors:
                    if m not in existing.mirrors:
                        existing.mirrors.append(m)
                if p.supports_auto_next:
                    existing.supports_auto_next = True
                if p.supports_4k:
                    existing.supports_4k = True
                if p.status_page and not existing.status_page:
                    existing.status_page = p.status_page
            else:
                consolidated[p.key] = p

        return list(consolidated.values())

    def sync_to_db(self, providers: List[ParsedProvider]) -> int:
        """Syncs parsed providers and their mirrors into ripperdb SQLite."""
        if not self.cache:
            return 0

        synced_count = 0
        for p in providers:
            self.cache.upsert_provider(
                provider_id=p.key,
                name=p.name,
                archetype=p.archetype,
                primary_url=p.primary_url,
                section=p.section,
                supports_auto_next=p.supports_auto_next,
                supports_4k=p.supports_4k,
            )

            for i, mirror in enumerate(p.mirrors):
                mirror_domain = clean_domain(mirror)
                self.cache.upsert_mirror(
                    provider_id=p.key,
                    mirror_url=mirror,
                    mirror_domain=mirror_domain,
                    is_primary=(i == 0),
                    is_active=True,
                )
            synced_count += 1

        logger.info("Successfully synced %d providers into ripperdb", synced_count)
        return synced_count

    def update_watchdog_registry(self, providers: List[ParsedProvider]) -> None:
        """
        Atomically updates ripper/hoster_watchdog/domain_registry.json
        with newly discovered mirrors without overwriting latency metrics.
        """
        existing_data: Dict[str, Any] = {"version": "1.0.0", "providers": {}}
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8-sig") as f:
                    existing_data = json.load(f)
            except Exception as e:
                logger.warning("Could not read existing domain_registry.json: %s", e)

        providers_dict = existing_data.get("providers", {})

        for p in providers:
            if p.key in providers_dict:
                rec = providers_dict[p.key]
                existing_mirrors = rec.get("mirrors", [])
                for m in p.mirrors:
                    if m not in existing_mirrors:
                        existing_mirrors.append(m)
                rec["mirrors"] = existing_mirrors
                if not rec.get("primary"):
                    rec["primary"] = p.primary_url
            else:
                providers_dict[p.key] = {
                    "name": p.name,
                    "primary": p.primary_url,
                    "mirrors": p.mirrors,
                    "active_mirror": p.primary_url,
                    "status": "online",
                    "latency_ms": 0.0,
                }

        existing_data["providers"] = providers_dict

        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.registry_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(self.registry_path)
        logger.info("Atomically updated domain_registry.json with %d providers", len(providers_dict))

    def get_seed_markdown(self) -> str:
        """Loads bundled FMHY video seed markdown from ripperdb package data."""
        if SEED_FILE_PATH.exists():
            return SEED_FILE_PATH.read_text(encoding="utf-8")
        return ""

    def fetch_live_html(self) -> Optional[str]:
        """Fetches live HTML content directly from https://fmhy.net/video."""
        # 1. Attempt curl_cffi with Chrome 124 TLS impersonation
        try:
            from curl_cffi import requests as cffi_requests
            resp = cffi_requests.get(FMHY_VIDEO_URL, impersonate="chrome124", timeout=12.0)
            if resp.status_code == 200 and len(resp.text) > 5000:
                logger.info("Successfully fetched live FMHY HTML from %s via curl_cffi (%d bytes)", FMHY_VIDEO_URL, len(resp.text))
                return resp.text
        except Exception as e:
            logger.debug("curl_cffi fetch failed for %s: %s", FMHY_VIDEO_URL, e)

        # 2. Attempt httpx client
        try:
            import httpx
            resp = httpx.get(FMHY_VIDEO_URL, timeout=12.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and len(resp.text) > 5000:
                logger.info("Successfully fetched live FMHY HTML from %s via httpx (%d bytes)", FMHY_VIDEO_URL, len(resp.text))
                return resp.text
        except Exception as e:
            logger.debug("httpx fetch failed for %s: %s", FMHY_VIDEO_URL, e)

        return None

    def fetch_live_markdown(self) -> Optional[str]:
        """Fetches live markdown content from GitHub raw docs or fmhy.net."""
        targets = [FMHY_GITHUB_RAW_URL, FMHY_VIDEO_URL]
        for url in targets:
            # 1. Attempt curl_cffi with Chrome 124 TLS impersonation
            try:
                from curl_cffi import requests as cffi_requests
                resp = cffi_requests.get(url, impersonate="chrome124", timeout=10.0)
                if resp.status_code == 200 and len(resp.text) > 1000:
                    logger.info("Successfully fetched live FMHY markdown from %s via curl_cffi", url)
                    return resp.text
            except Exception as e:
                logger.debug("curl_cffi fetch failed for %s: %s", url, e)

            # 2. Attempt httpx client
            try:
                import httpx
                resp = httpx.get(url, timeout=10.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200 and len(resp.text) > 1000:
                    logger.info("Successfully fetched live FMHY markdown from %s via httpx", url)
                    return resp.text
            except Exception as e:
                logger.debug("httpx fetch failed for %s: %s", url, e)

        return None

    def load_markdown(self, force_live: bool = False) -> Tuple[str, str]:
        """
        Loads FMHY markdown, attempting live fetch first if requested or available,
        falling back seamlessly to bundled seed markdown.
        """
        if force_live:
            live_text = self.fetch_live_markdown()
            if live_text:
                return live_text, "live"

        # Try live if not forced, but quickly fallback
        live_text = self.fetch_live_markdown()
        if live_text:
            return live_text, "live"

        seed_text = self.get_seed_markdown()
        if seed_text:
            logger.info("Loaded bundled FMHY video seed directory (%d bytes)", len(seed_text))
            return seed_text, "bundled_seed"

        return "", "empty"

    def crawl_live_and_diff(self, update_watchdog: bool = True) -> Dict[str, Any]:
        """
        Deep-crawls both live HTML (https://fmhy.net/video) and live Markdown
        (GitHub raw docs), parses both, merges them to guarantee 100% link coverage,
        calculates diffs against existing database, syncs SQLite, and updates watchdog registry.
        """
        sources_crawled: List[str] = []
        all_providers_map: Dict[str, ParsedProvider] = {}

        # 1. Fetch & Parse Live HTML
        html_content = self.fetch_live_html()
        if html_content:
            sources_crawled.append("live_html (fmhy.net/video)")
            html_provs = self.parse_html(html_content)
            for p in html_provs:
                all_providers_map[p.key] = p
            logger.info("Parsed %d providers from live HTML", len(html_provs))

        # 2. Fetch & Parse Live Markdown
        md_content = self.fetch_live_markdown()
        if md_content:
            sources_crawled.append("live_markdown (github/FMHYEdit)")
            md_provs = self.parse_markdown(md_content)
            for p in md_provs:
                if p.key in all_providers_map:
                    existing = all_providers_map[p.key]
                    for m in p.mirrors:
                        if m not in existing.mirrors:
                            existing.mirrors.append(m)
                    if p.supports_auto_next:
                        existing.supports_auto_next = True
                    if p.supports_4k:
                        existing.supports_4k = True
                    if p.status_page and not existing.status_page:
                        existing.status_page = p.status_page
                else:
                    all_providers_map[p.key] = p
            logger.info("Merged providers from live Markdown (total unique now %d)", len(all_providers_map))

        # Fallback to bundled seed if both network fetches failed
        if not all_providers_map:
            seed_content = self.get_seed_markdown()
            if seed_content:
                sources_crawled.append("bundled_seed")
                seed_provs = self.parse_markdown(seed_content)
                for p in seed_provs:
                    all_providers_map[p.key] = p

        if not all_providers_map:
            return {
                "success": False,
                "status": "failed",
                "sources_crawled": sources_crawled,
                "providers_total": 0,
                "mirrors_total": 0,
                "new_providers_count": 0,
                "new_mirrors_count": 0,
                "new_providers": [],
                "new_mirrors": [],
                "error": "No providers could be crawled or loaded",
            }

        merged_providers = list(all_providers_map.values())

        # 3. Calculate Diff against existing DB
        existing_prov_keys = set()
        existing_mirror_domains = set()
        if self.cache:
            try:
                conn = self.cache._get_connection() if hasattr(self.cache, "_get_connection") else getattr(self.cache, "_conn", None)
                if conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM providers")
                    existing_prov_keys = {r[0] for r in cur.fetchall()}
                    cur.execute("SELECT mirror_domain FROM domain_mirrors")
                    existing_mirror_domains = {r[0] for r in cur.fetchall()}
            except Exception as e:
                logger.debug("Could not inspect existing DB for diff: %s", e)

        new_providers_list = []
        new_mirrors_list = []

        for p in merged_providers:
            if p.key not in existing_prov_keys:
                new_providers_list.append({
                    "id": p.key,
                    "name": p.name,
                    "primary_url": p.primary_url,
                    "section": p.section,
                    "archetype": p.archetype,
                    "mirrors_count": len(p.mirrors),
                })
            for m in p.mirrors:
                m_dom = clean_domain(m)
                if m_dom and m_dom not in existing_mirror_domains:
                    new_mirrors_list.append({
                        "provider_id": p.key,
                        "mirror_url": m,
                        "mirror_domain": m_dom,
                    })

        # 4. Sync to SQLite DB
        synced_count = self.sync_to_db(merged_providers)
        total_mirrors = sum(len(p.mirrors) for p in merged_providers)

        # 5. Atomically update watchdog domain_registry.json
        if update_watchdog:
            self.update_watchdog_registry(merged_providers)

        sections: Dict[str, int] = {}
        for p in merged_providers:
            sections[p.section] = sections.get(p.section, 0) + 1

        return {
            "success": True,
            "status": "success",
            "sources_crawled": sources_crawled,
            "providers_total": len(merged_providers),
            "mirrors_total": total_mirrors,
            "new_providers_count": len(new_providers_list),
            "new_mirrors_count": len(new_mirrors_list),
            "new_providers": new_providers_list,
            "new_mirrors": new_mirrors_list,
            "archetypes": sections,
        }

    def sync_all(self, force_live: bool = False, update_watchdog: bool = True) -> Dict[str, Any]:
        """
        Executes end-to-end sync pipeline:
        1. Loads markdown (live fetch with bundled fallback)
        2. Parses providers and mirrors (excluding live tv/sports/iptv)
        3. Upserts providers and mirrors into ripperdb SQLite
        4. Atomically updates ripper's domain_registry.json
        """
        content, source = self.load_markdown(force_live=force_live)
        if not content:
            logger.error("Failed to load any FMHY video content (live and seed both unavailable)")
            return {
                "success": False,
                "source": "none",
                "providers_synced": 0,
                "total_mirrors": 0,
            }

        providers = self.parse_markdown(content)
        synced_count = self.sync_to_db(providers)

        total_mirrors = sum(len(p.mirrors) for p in providers)
        sections: Dict[str, int] = {}
        for p in providers:
            sections[p.section] = sections.get(p.section, 0) + 1

        if update_watchdog:
            self.update_watchdog_registry(providers)

        return {
            "success": True,
            "source": source,
            "providers_synced": synced_count,
            "total_mirrors": total_mirrors,
            "sections": sections,
        }

    def sync(self, force: bool = False, update_watchdog: bool = True, crawl_live: bool = False) -> Dict[str, Any]:
        """Convenience alias for sync_all or crawl_live_and_diff."""
        if crawl_live:
            return self.crawl_live_and_diff(update_watchdog=update_watchdog)
        res = self.sync_all(force_live=force, update_watchdog=update_watchdog)
        return {
            "status": "success" if res.get("success") else "failed",
            "source": res.get("source"),
            "providers_total": res.get("providers_synced", 0),
            "mirrors_total": res.get("total_mirrors", 0),
            "archetypes": res.get("sections", {}),
            **res,
        }

