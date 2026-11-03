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

url = "https://d000d.com/e/f1jy0udr99xa"
session = requests.Session(impersonate="chrome120")
headers = {
    "Referer": "https://leakdom.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 1. Fetch embed page
r = session.get(url, headers=headers, timeout=10)
print("EMBED STATUS:", r.status_code)

# 2. Extract pass_md5 full path
m = re.search(r"['\"]/pass_md5/([^/'\"]+)/([^'\"]+)['\"]", r.text)
if not m:
    m = re.search(r"/pass_md5/([^\s'\"<>\)]+)", r.text)
    if m:
        parts = m.group(1).split("/")
        hash_val = parts[0]
        token_val = parts[1] if len(parts) > 1 else ""
else:
    hash_val = m.group(1)
    token_val = m.group(2)

print("HASH:", hash_val)
print("TOKEN:", token_val)

domain = r.url.split("/")[2]
pass_url = f"https://{domain}/pass_md5/{hash_val}/{token_val}" if token_val else f"https://{domain}/pass_md5/{hash_val}"
print("PASS URL:", pass_url)

# 3. Get pass CDN prefix
p_resp = session.get(pass_url, headers={"Referer": r.url})
prefix = p_resp.text.strip()
print("CDN PREFIX:", prefix)

# 4. Construct makePlay() string
rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
expiry = int(time.time() * 1000)
direct_mp4 = f"{prefix}{rand_str}?token={token_val}&expiry={expiry}"
print("🔥 CONSTRUCTED DIRECT MP4 URL:")
print(direct_mp4)

# 5. Fetch 1MB byte slice
dl_headers = {
    "Referer": f"https://{domain}/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Range": "bytes=0-1048575"
}

dl_resp = session.get(direct_mp4, headers=dl_headers, timeout=15)
print("CHUNK STATUS:", dl_resp.status_code)
print("CHUNK CONTENT-TYPE:", dl_resp.headers.get("content-type"))
print("CHUNK LENGTH:", len(dl_resp.content))
print("FIRST 16 BYTES HEX:", dl_resp.content[:16].hex())
if dl_resp.content[:4] == b"\x00\x00\x00\x18" or dl_resp.content[:4] == b"\x00\x00\x00\x20" or b"ftyp" in dl_resp.content[:32] or b"matroska" in dl_resp.content[:32]:
    print("🏆 SUCCESS! 100% REAL MP4 BINARY VIDEO CHUNK VERIFIED!")
else:
    print("BODY TEXT:", dl_resp.content[:100])
