import httpx

url = "https://playmate.to/api/v"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://playmate.to/embed/a4Udh8zBaBVGW",
    "Origin": "https://playmate.to",
    "Content-Type": "application/json"
}

# Check variations for payload
payloads = [
    {"filecode": "a4Udh8zBaBVGW"},
    {"code": "a4Udh8zBaBVGW"},
    {"id": "a4Udh8zBaBVGW"},
    {"hash": "a4Udh8zBaBVGW"},
    {"v": "a4Udh8zBaBVGW"},
    {"key": "a4Udh8zBaBVGW"}
]

with httpx.Client(verify=False) as client:
    for p in payloads:
        r = client.post(url, headers=headers, json=p)
        print(f"PAYLOAD {p} -> [{r.status_code}] {r.text}")
