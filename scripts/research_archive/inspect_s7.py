import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import httpx
from bs4 import BeautifulSoup

embed_url = 'https://vidara.to/e/Er1HRIp8JMMDm'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Referer': 'https://leakdom.com/'
}

r = httpx.get(embed_url, headers=headers, verify=False, follow_redirects=True)
soup = BeautifulSoup(r.text, 'html.parser')
scripts = soup.find_all('script')
s7 = scripts[7].get_text()

with open("script7.js", "w", encoding="utf-8") as f:
    f.write(s7)

print("Saved script7.js, length:", len(s7))
