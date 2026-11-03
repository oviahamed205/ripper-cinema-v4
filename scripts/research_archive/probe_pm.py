import httpx

endpoints = [
    "https://playmate.to/api/v1/stream",
    "https://playmate.to/api/video",
    "https://playmate.to/api/get",
    "https://playmate.to/api/play",
    "https://playmate.to/api/sources",
    "https://playmate.to/api/e/a4Udh8zBaBVGW",
    "https://playmate.to/v/a4Udh8zBaBVGW",
    "https://playmate.to/d/a4Udh8zBaBVGW"
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://playmate.to/embed/a4Udh8zBaBVGW"
}

with httpx.Client(verify=False) as client:
    for ep in endpoints:
        r = client.get(ep, headers=headers)
        print(f"[{r.status_code}] GET {ep} -> {r.text[:150]}")
