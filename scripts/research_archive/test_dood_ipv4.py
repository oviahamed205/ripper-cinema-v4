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

# Force IPv4
session = requests.Session(impersonate="chrome120")
session.headers.update({
    "Referer": "https://leakdom.com/",
    "Accept-Language": "en-US,en;q=0.9",
})

# 1. Embed page
r = session.get(url, timeout=10)
print("EMBED STATUS:", r.status_code)
m = re.search(r"/pass_md5/([^'\"]+)", r.text)
if m:
    pass_token = m.group(1)
    domain = r.url.split("/")[2]
    pass_url = f"https://{domain}/pass_md5/{pass_token}"
    
    # 2. Pass md5
    p_resp = session.get(pass_url, headers={"Referer": r.url})
    prefix = p_resp.text.strip()
    
    # 3. Direct URL
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    ts = int(time.time() * 1000)
    direct_mp4 = f"{prefix}{rand_str}?token={pass_token}&expiry={ts}"
    print("DIRECT URL:", direct_mp4)
    
    # 4. Stream request with cookies from session
    dl_headers = {
        "Referer": f"https://{domain}/",
        "User-Agent": session.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    }
    dl_resp = session.get(direct_mp4, headers=dl_headers, timeout=15)
    print("DL STATUS:", dl_resp.status_code)
    print("DL CONTENT-TYPE:", dl_resp.headers.get("content-type"))
    print("DL CONTENT-LENGTH:", len(dl_resp.content))
    print("DL SNIPPET:", dl_resp.content[:60])
