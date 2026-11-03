import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from unshorten.proxy_engine import ensure_proxy_running, is_proxy_alive, get_proxied_stream_url
from curl_cffi import requests
import re
import time
import random
import string
import httpx

# Ensure proxy is up
ensure_proxy_running()
print("IS PROXY ALIVE:", is_proxy_alive())

# Test 1: DoodStream URL
url = "https://d000d.com/e/f1jy0udr99xa"
session = requests.Session(impersonate="chrome120")
r = session.get(url, headers={"Referer": "https://leakdom.com/"})
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
print("DOOD DIRECT MP4:", direct_mp4)

# Get proxied URL for PotPlayer
proxied_dood_url = get_proxied_stream_url(direct_mp4, referer=f"https://{domain}/")
print("PROXIED DOOD URL:", proxied_dood_url)

# Test fetching 256KB from the proxy
r_prox = httpx.get(proxied_dood_url, headers={"Range": "bytes=0-262143"}, timeout=10)
print("PROXY DOOD STATUS:", r_prox.status_code)
print("PROXY DOOD CONTENT-TYPE:", r_prox.headers.get("content-type"))
print("PROXY DOOD CONTENT-LENGTH:", len(r_prox.content))
print("FIRST 16 BYTES HEX:", r_prox.content[:16].hex())
if r_prox.content[:4] == b"\x00\x00\x00\x18" or r_prox.content[:4] == b"\x00\x00\x00\x20" or b"ftyp" in r_prox.content[:32] or b"matroska" in r_prox.content[:32]:
    print("🏆🏆🏆 TEST 1 PASSED: DOODSTREAM DIRECT MP4 BINARY PLAYABLE OVER PROXY!")
else:
    print("BODY TEXT:", r_prox.content[:100])
