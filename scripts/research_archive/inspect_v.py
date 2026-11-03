import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import httpx
from bs4 import BeautifulSoup
import re

url = "https://vidara.to/v/Er1HRIp8JMMDm"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://leakdom.com/"
}

r = httpx.get(url, headers=headers, verify=False, follow_redirects=True)
print("STATUS:", r.status_code)
print("URL:", r.url)
soup = BeautifulSoup(r.text, "html.parser")
print("TITLE:", soup.title)

# Look for download button or direct video links
for a in soup.find_all("a", href=True):
    print("A TAG:", a.get_text().strip(), "->", a["href"])

for v in soup.find_all(["video", "source"]):
    print("VIDEO/SRC:", v)

for s in soup.find_all("script"):
    txt = s.get_text()
    if any(k in txt.lower() for k in ["m3u8", "mp4", "download", "hls", "file"]):
        print("SCRIPT:", txt[:400])
