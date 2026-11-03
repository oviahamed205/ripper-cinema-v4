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

# 1. Detect public IP that connects to cloudflare
session = requests.Session(impersonate="chrome120")
ip_resp = session.get("https://api.ipify.org")
my_ip = ip_resp.text.strip()
print("DETECTED EGRESS IP:", my_ip)

url = "https://d000d.com/e/f1jy0udr99xa"
headers = {
    "Referer": "https://leakdom.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

r = session.get(url, headers=headers, timeout=10)
html = r.text
domain = r.url.split("/")[2]

m = re.search(r"['\"]/pass_md5/([^/'\"]+)/([^'\"]+)['\"]", html)
if not m:
    m = re.search(r"/pass_md5/([^\s'\"<>\)]+)", html)
    parts = m.group(1).split("/")
    hash_val = parts[0]
    token_val = parts[1] if len(parts) > 1 else ""
else:
    hash_val = m.group(1)
    token_val = m.group(2)

print("HASH:", hash_val)
print("TOKEN:", token_val)

# 2. Get CDN prefix
pass_url = f"https://{domain}/pass_md5/{hash_val}/{token_val}"
p_resp = session.get(pass_url, headers={"Referer": r.url})
prefix = p_resp.text.strip()
print("PREFIX:", prefix)

# 3. Watch handshake
m_oemb = re.search(r'var oemb\s*=\s*["\']([^"\']*)["\']', html)
oemb = m_oemb.group(1) if m_oemb else "1"
m_oref = re.search(r'var oref\s*=\s*["\']([^"\']*)["\']', html)
oref = m_oref.group(1) if m_oref else "https://leakdom.com/"
m_oftor = re.search(r'var oftor\s*=\s*["\']([^"\']*)["\']', html)
oftor = m_oftor.group(1) if m_oftor else ""

watch_url = f"https://{domain}/dood?op=watch&hash={hash_val}&token={token_val}&embed={oemb}&ref2={urllib.parse.quote(oref)}&adb=0&ftor={oftor}"
w_resp = session.get(watch_url, headers={"Referer": r.url, "X-Requested-With": "XMLHttpRequest"})
print("WATCH STATUS:", w_resp.status_code, "BODY:", w_resp.text)

rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
expiry = int(time.time() * 1000)
direct_mp4 = f"{prefix}{rand_str}?token={token_val}&expiry={expiry}"
print("DIRECT MP4:", direct_mp4)

dl_headers = {
    "Referer": f"https://{domain}/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Range": "bytes=0-1048575"
}

# Try with curl_cffi session
dl_resp = session.get(direct_mp4, headers=dl_headers, timeout=15)
print("DL STATUS:", dl_resp.status_code)
print("DL CONTENT-TYPE:", dl_resp.headers.get("content-type"))
print("DL LENGTH:", len(dl_resp.content))
if dl_resp.content[:4] == b"\x00\x00\x00\x18" or dl_resp.content[:4] == b"\x00\x00\x00\x20" or b"ftyp" in dl_resp.content[:32] or b"matroska" in dl_resp.content[:32]:
    print("🏆 SUCCESS! 100% REAL MP4 BINARY VIDEO CHUNK VERIFIED!")
else:
    print("DL TEXT:", dl_resp.content[:100])
