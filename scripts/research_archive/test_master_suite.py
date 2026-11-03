import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import asyncio
from unshorten.anystream import extract_any_streams
from unshorten.proxy_engine import get_proxied_stream_url, is_proxy_alive, ensure_proxy_running
import httpx

ensure_proxy_running()

test_cases = [
    ("DoodStream Direct Link", "https://d000d.com/e/f1jy0udr99xa"),
    ("PlayMate Embedded Webpage", "https://leakdom.com/15700/mother-giving-pleasure-to-her-own-son-taboo-porn/"),
    ("Vidara Embedded Webpage", "https://leakdom.com/14871/chinese-real-brother-sister-taboo-sex-darkclip/"),
]

for label, test_url in test_cases:
    print(f"\n==========================================")
    print(f"TESTING: {label}")
    print(f"URL: {test_url}")
    print(f"==========================================")
    
    streams = asyncio.run(extract_any_streams(test_url))
    if not streams:
        print(f"❌ FAILED to extract streams for {label}")
        sys.exit(1)
        
    for s in streams:
        print(f"✔ Extracted: {s['title']}")
        print(f"✔ Quality:   {s['quality']}")
        print(f"✔ URL:       {s['url'][:70]}...")
        
        prox_url = get_proxied_stream_url(s['url'], s.get('referer', ''))
        r = httpx.get(prox_url, headers={"Range": "bytes=0-131071"}, timeout=10)
        print(f"✔ Proxy HTTP Status: {r.status_code}")
        print(f"✔ Content-Type:      {r.headers.get('content-type')}")
        print(f"✔ Bytes Received:    {len(r.content)}")
        assert r.status_code in [200, 206], f"Unexpected status {r.status_code}"
        assert len(r.content) > 0, "No content received"
        print(f"🏆 {label} VERIFIED 100% OPERATIONAL!")

print("\n🎉🎉🎉 ALL TESTS PASSED WITH ZERO ERRORS! SYSTEM READY FOR LAST SHIP!")
