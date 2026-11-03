import httpx

endpoints = [
    "https://playmate.to/api/stream",
    "https://playmate.to/api/source",
    "https://playmate.to/api/player",
    "https://playmate.to/api/v",
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://playmate.to/embed/a4Udh8zBaBVGW",
    "Origin": "https://playmate.to",
    "Content-Type": "application/json"
}

payload = {
    "filecode": "a4Udh8zBaBVGW",
    "id": "a4Udh8zBaBVGW",
    "code": "a4Udh8zBaBVGW",
    "device": "web"
}

with httpx.Client(verify=False) as client:
    for ep in endpoints:
        r = client.post(ep, headers=headers, json=payload)
        print(f"[{r.status_code}] {ep} -> {r.text[:200]}")
