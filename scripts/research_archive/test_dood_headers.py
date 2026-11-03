import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from curl_cffi import requests
import re
import time
import random
import string
import urllib.parse

session = requests.Session(impersonate="chrome120")
url = "https://d000d.com/e/f1jy0udr99xa"
headers = {"Referer": "https://leakdom.com/"}
r = session.get(url, headers=headers)
html = r.text
domain = r.url.split("/")[2]

m = re.search(r"['\"]/pass_md5/([^/'\"]+)/([^'\"]+)['\"]", html)
hash_val = m.group(1)
token_val = m.group(2)

pass_url = f"https://{domain}/pass_md5/{hash_val}/{token_val}"
p_resp = session.get(pass_url, headers={"Referer": r.url})
prefix = p_resp.text.strip()

rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
expiry = int(time.time() * 1000)
direct_mp4 = f"{prefix}{rand_str}?token={token_val}&expiry={expiry}"

for header_ip in ["X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP", "True-Client-IP"]:
    dl_headers = {
        "Referer": f"https://{domain}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Range": "bytes=0-1048575",
        header_ip: "113.21.230.163"
    }
    dl_resp = session.get(direct_mp4, headers=dl_headers, timeout=5)
    print(f"HEADER [{header_ip}] STATUS: {dl_resp.status_code}, SNIPPET: {dl_resp.content[:30]}")
