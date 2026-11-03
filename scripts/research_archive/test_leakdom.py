import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse

# 1. Fetch main page
url = "https://leakdom.com/14871/chinese-real-brother-sister-taboo-sex-darkclip/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://leakdom.com/"
}

r = httpx.get(url, headers=headers, verify=False, follow_redirects=True)
soup = BeautifulSoup(r.text, "html.parser")
title = soup.title.get_text().strip() if soup.title else "LeakDom Video"
print("TITLE:", title)

# Find iframe
iframe = soup.find("iframe")
if iframe:
    iframe_src = iframe["src"]
    print("IFRAME SRC:", iframe_src)
    
    # Check if vidara
    if "vidara" in iframe_src:
        filecode = iframe_src.rstrip("/").split("/")[-1]
        print("VIDARA FILECODE:", filecode)
        
        # In AnyStream, we provide the clean embedded player URL and direct embed link
        # with pipe Referer for PotPlayer and browser playback
        direct_stream_player = f"https://vidarae.live/e/{filecode}|Referer=https://leakdom.com/"
        print("PLAYABLE STREAM EMBED:", direct_stream_player)
