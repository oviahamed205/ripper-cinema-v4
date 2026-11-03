import httpx
from bs4 import BeautifulSoup
import re

embed_url = 'https://vidara.to/e/Er1HRIp8JMMDm'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Referer': 'https://leakdom.com/'
}

r = httpx.get(embed_url, headers=headers, verify=False, follow_redirects=True)
soup = BeautifulSoup(r.text, 'html.parser')

for idx, s in enumerate(soup.find_all('script')):
    txt = s.get_text().strip()
    if 'eval' in txt or 'decode' in txt or 'sources' in txt or 'file' in txt or 'hls' in txt or 'setup' in txt:
        print(f"=== SCRIPT {idx} ({len(txt)} chars) ===")
        print(txt[:600])
        print("...")
