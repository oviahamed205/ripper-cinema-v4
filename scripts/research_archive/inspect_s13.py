import httpx
from bs4 import BeautifulSoup
import urllib.parse

embed_url = 'https://vidara.to/e/Er1HRIp8JMMDm'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Referer': 'https://leakdom.com/'
}

r = httpx.get(embed_url, headers=headers, verify=False, follow_redirects=True)
soup = BeautifulSoup(r.text, 'html.parser')
scripts = soup.find_all('script')
s13 = scripts[13].get_text()

# Decode s13
decoded_str = urllib.parse.unquote(s13)
print("DECODED STR LENGTH:", len(decoded_str))

# Let's inspect script 13 full text
with open("script13.js", "w", encoding="utf-8") as f:
    f.write(s13)

print("Saved script13.js")
