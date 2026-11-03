import httpx
import re
import time
import random
import string

url = 'https://d000d.com/e/f1jy0udr99xa'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Referer': 'https://d000d.com/'
}

r = httpx.get(url, headers=headers, verify=False, follow_redirects=True)
print('STATUS:', r.status_code)
print('FINAL URL:', r.url)

# Doodstream pass_md5 pattern:
m = re.search(r"/pass_md5/([^'\"]+)", r.text)
if m:
    pass_token = m.group(1)
    pass_url = f"https://d000d.com/pass_md5/{pass_token}"
    print('PASS URL:', pass_url)
    p_resp = httpx.get(pass_url, headers={'Referer': str(r.url), 'User-Agent': headers['User-Agent']}, verify=False)
    print('PASS BODY:', p_resp.text)
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    ts = int(time.time() * 1000)
    direct_mp4 = f"{p_resp.text}{rand_str}?token={pass_token}&expiry={ts}"
    print('DIRECT DOOD MP4:', direct_mp4)
