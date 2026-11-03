import httpx
import re
import time
import random
import string

url = 'https://d000d.com/e/f1jy0udr99xa'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Dest': 'iframe',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'cross-site',
    'Referer': 'https://leakdom.com/'
}

with httpx.Client(verify=False, follow_redirects=True) as client:
    r = client.get(url, headers=headers)
    print('STATUS:', r.status_code)
    print('URL:', r.url)
    print('BODY LENGTH:', len(r.text))
    m = re.search(r"/pass_md5/([^'\"]+)", r.text)
    if m:
        print('FOUND PASS MD5:', m.group(1))
    else:
        print('BODY SNIPPET:', r.text[:300])
