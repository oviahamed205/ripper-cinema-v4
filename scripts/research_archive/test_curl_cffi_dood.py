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

r = session.get(url, headers=headers, timeout=10)
print("STATUS:", r.status_code)
print("FINAL URL:", r.url)
print("BODY LENGTH:", len(r.text))

m = re.search(r"/pass_md5/([^'\"]+)", r.text)
if m:
    pass_token = m.group(1)
    print("FOUND pass_md5 TOKEN:", pass_token)
    domain = r.url.split("/")[2]
    pass_url = f"https://{domain}/pass_md5/{pass_token}"
    print("FETCHING PASS URL:", pass_url)
    
    time.sleep(1)
    p_resp = session.get(pass_url, headers={"Referer": r.url})
    print("PASS BODY:", p_resp.text)
    
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    ts = int(time.time() * 1000)
    direct_mp4 = f"{p_resp.text}{rand_str}?token={pass_token}&expiry={ts}"
    print("🔥 DIRECT MP4 STREAM URL:")
    print(direct_mp4)
    
    # Test head request
    head_resp = session.head(direct_mp4, headers={"Referer": f"https://{domain}/"})
    print("TARGET HEAD STATUS:", head_resp.status_code)
    print("CONTENT LENGTH:", head_resp.headers.get("content-length"))
    print("CONTENT TYPE:", head_resp.headers.get("content-type"))
else:
    print("SNIPPET:", r.text[:300])
