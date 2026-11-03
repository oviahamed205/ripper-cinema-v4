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
soup = BeautifulSoup(r.text, "html.parser")

for t in ["txt-download", "txt-forum", "txt-html", "txt-embed"]:
    el = soup.find(id=t)
    print(t, ":", el.get_text().strip() if el else "None")

# Check all textareas or inputs
for ta in soup.find_all(["textarea", "input"]):
    print("TAG:", ta.get("id"), ta.get("name"), "=", ta.get_text() or ta.get("value"))
