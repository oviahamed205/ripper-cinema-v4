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

print('--- ALL SCRIPTS ---')
for idx, s in enumerate(soup.find_all('script')):
    txt = s.get_text().strip()
    if txt:
        print(f"=== SCRIPT {idx} ===")
        print(txt)
        print("="*40)
