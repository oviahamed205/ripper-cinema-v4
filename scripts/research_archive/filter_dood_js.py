import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from curl_cffi import requests
from bs4 import BeautifulSoup

url = "https://d000d.com/e/f1jy0udr99xa"
session = requests.Session(impersonate="chrome120")
r = session.get(url, headers={"Referer": "https://leakdom.com/"})
soup = BeautifulSoup(r.text, "html.parser")

for idx, s in enumerate(soup.find_all("script")):
    t = s.get_text().strip()
    if t and any(k in t for k in ["pass_md5", "makePlay", "player", "md5", "token"]):
        print(f"=== RELEVANT SCRIPT {idx} ===")
        print(t)
