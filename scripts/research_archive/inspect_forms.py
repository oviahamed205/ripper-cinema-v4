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

for form in soup.find_all("form"):
    print("FORM ACTION:", form.get("action"))
    for inp in form.find_all("input"):
        print("  INPUT:", inp.get("name"), "=", inp.get("value"))

for btn in soup.find_all(["button"]):
    print("BTN:", btn)

for s in soup.find_all("script"):
    t = s.get_text()
    if any(k in t.lower() for k in ["download", "ajax", "post", "fetch", "op", "file_code"]):
        print("SCRIPT AJAX/POST:", t[:500])
