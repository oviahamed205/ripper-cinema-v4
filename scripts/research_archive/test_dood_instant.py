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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

# 1. Load embed page
r = session.get(url, headers=headers, timeout=10)
m = re.search(r"/pass_md5/([^'\"]+)", r.text)
if m:
    pass_token = m.group(1)
    domain = r.url.split("/")[2]
    pass_url = f"https://{domain}/pass_md5/{pass_token}"
    
    # 2. Get pass prefix
    p_resp = session.get(pass_url, headers={"Referer": r.url})
    prefix = p_resp.text.strip()
    
    # 3. Construct direct download URL
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    ts = int(time.time() * 1000)
    direct_mp4 = f"{prefix}{rand_str}?token={pass_token}&expiry={ts}"
    print("DIRECT URL:", direct_mp4)
    
    # 4. Stream 512KB chunk with Referer
    dl_headers = {
        "Referer": f"https://{domain}/",
        "Range": "bytes=0-524287",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    }
    dl_resp = session.get(direct_mp4, headers=dl_headers, timeout=10)
    print("STATUS:", dl_resp.status_code)
    print("CONTENT TYPE:", dl_resp.headers.get("content-type"))
    print("BODY LENGTH:", len(dl_resp.content))
    print("FIRST 16 BYTES HEX:", dl_resp.content[:16].hex())
    if dl_resp.content[:4] == b"\x00\x00\x00\x18" or dl_resp.content[:4] == b"\x00\x00\x00\x20" or b"ftyp" in dl_resp.content[:32] or b"matroska" in dl_resp.content[:32]:
        print("🎉 SUCCESS! 100% REAL VIDEO BINARY RECEIVED!")
    else:
        print("TEXT IF ANY:", dl_resp.content[:100])
