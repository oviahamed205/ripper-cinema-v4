from __future__ import annotations
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urldefrag
import re
from bs4 import BeautifulSoup
from .models import Post

MEDIA_EXTENSIONS = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".m3u8", ".ts")
IGNORE_PARTS = {"category","tag","author","page","contact","privacy","login","register","feed","about","dmca"}
GATEWAYS = (
    "r2.dev", "gdflix", "linkos", "pixeldrain", "vcloud", "hubcloud", "gofile",
    "filepress", "gdtot", "mediafire", "nexdrive", "katdrive", "megaup", "magiclinks",
    "krakenfiles", "links.hdmovieshub", "links.kmhd", "drive.google.com"
)


def hidden(element) -> bool:
    for node in [element, *list(element.parents)]:
        if not hasattr(node,"get"): continue
        if node.has_attr("hidden") or node.get("aria-hidden") == "true": return True
        style = re.sub(r"\s+", "", str(node.get("style",""))).lower()
        if "display:none" in style or "visibility:hidden" in style or re.search(r"(?:^|;)opacity:0(?:;|$)",style): return True
        if set(node.get("class",[])) & {"honeypot","trap","d-none","hidden-link","sr-only"}: return True
    return False


def normalize_date(value):
    if not value: return None
    try:
        d = datetime.fromisoformat(value.replace("Z","+00:00"))
        if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except (TypeError,ValueError): return None


def discover_posts(html: str, base_url: str, limit: int) -> list[Post]:
    soup=BeautifulSoup(html,"html.parser")
    base_host=(urlsplit(base_url).hostname or "").lower()
    scope=soup.select_one("main") or soup
    output=[]; seen=set()
    for a in scope.find_all("a",href=True):
        if hidden(a): continue
        full=urldefrag(urljoin(base_url,a["href"].strip()))[0]
        p=urlsplit(full)
        if p.scheme not in {"http","https"} or (p.hostname or "").lower()!=base_host: continue
        if not p.path.strip("/") or set(p.path.lower().strip("/").split("/")) & IGNORE_PARTS: continue
        if p.path.lower().endswith(MEDIA_EXTENSIONS): continue
        title=a.get_text(" ",strip=True)
        if not title:
            img=a.find("img"); title=img.get("alt","").strip() if img else ""
        if len(title)<8 or full in seen: continue
        seen.add(full)
        article=a.find_parent("article") or a.parent
        stamp=article.find("time") if article else None
        date=normalize_date(stamp.get("datetime")) if stamp else None
        output.append(Post(full,title[:200],date))
    # Do not misrepresent an order when dates are missing on some cards.
    if output and all(p.published_at for p in output):
        output.sort(key=lambda p:p.published_at,reverse=True)
        for post in output: post.selection_basis="publication_date"
    return output[:limit]


def harvest_candidates(html: str, base_url: str, limit: int) -> list[str]:
    soup=BeautifulSoup(html,"html.parser")
    scope=(soup.select_one("article .entry-content") or soup.select_one(".entry-content")
           or soup.select_one("article") or soup.select_one("main") or soup)
    ranked=[]; seen=set()
    for item in scope.find_all(["a","button","video","source"]):
        if hidden(item): continue
        href=item.get("href") or item.get("src") or item.get("data-url") or item.get("data-href")
        if not href: continue
        url=urldefrag(urljoin(base_url,href))[0]; p=urlsplit(url)
        if p.scheme not in {"http","https"} or url==base_url or url in seen: continue
        text=item.get_text(" ",strip=True).lower()
        direct=p.path.lower().endswith(MEDIA_EXTENSIONS)
        is_r2="r2.dev" in (p.hostname or "").lower()
        gateway=any(g in (p.hostname or "").lower() for g in GATEWAYS)
        if direct or gateway or is_r2 or item.name in {"video","source"} or any(x in text for x in ("download","stream","watch","server","1080p","720p")):
            seen.add(url)
            # Rank priority: -1 = Cloudflare R2 (10Gbps CDN), 0 = Direct Media File, 1 = Gateway, 2 = General Link
            priority = -1 if is_r2 else (0 if direct else (1 if gateway else 2))
            ranked.append((priority, url))
    ranked.sort(key=lambda x:x[0])
    return [u for _,u in ranked[:limit]]
