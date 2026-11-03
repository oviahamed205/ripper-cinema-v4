import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from curl_cffi import requests

direct_url = "https://ef1093cl.cloudatacdn.com/u5kjzmueg3d3sdgge4uruly2drhjew55lhqpcefnxkkjzqh3hhfljfo5ivya/fl22vybgjo~3lDK9xOEFv?token=155118287-113-21-1788213404-1a86544297317f198ccf30cd8197505c/k34okpsw1otjd6oz8d5bkfvw&expiry=1788213392073"

session = requests.Session(impersonate="chrome120")
headers = {
    "Referer": "https://playmogo.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Range": "bytes=0-1048575" # 1MB slice
}

resp = session.get(direct_url, headers=headers, timeout=10)
print("STATUS CODE:", resp.status_code)
print("CONTENT TYPE:", resp.headers.get("content-type"))
print("CONTENT LENGTH:", len(resp.content))
print("FIRST 16 BYTES (HEX):", resp.content[:16].hex())
if b"ftyp" in resp.content[:32] or b"matroska" in resp.content[:32] or resp.content[:4] == b"\x00\x00\x00\x18" or resp.content[:4] == b"\x00\x00\x00\x20":
    print("✔ VERIFIED VALID MP4/MKV BINARY HEADER!")
else:
    print("BINARY SNIPPET:", resp.content[:32])
