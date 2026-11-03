import httpx

url = "https://playmate.to/api/v"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Referer": "https://playmate.to/embed/a4Udh8zBaBVGW",
    "Origin": "https://playmate.to",
    "Content-Type": "application/json"
}

# The window.__PM object in Script 6:
# window.__PM={color:"",logoUrl:"",logoPos:"",logoLink:"",share:false,videoId: 143665 ,referrer:"https:\/\/leakdom.com\/",countKey:"3a1b079aef785370f040f126cdb43d4e2a63a0da088d7e8e75943408764aa824",duration:0,poster:"https:\/\/wesa331.bestblogexist.com\/thumbnail\/a4Udh8zBaBVGW_2x2.jpg"};

payloads = [
    {"videoId": 143665},
    {"videoId": "143665"},
    {"id": 143665},
    {"key": "3a1b079aef785370f040f126cdb43d4e2a63a0da088d7e8e75943408764aa824"},
    {"countKey": "3a1b079aef785370f040f126cdb43d4e2a63a0da088d7e8e75943408764aa824"},
    {"videoId": 143665, "key": "3a1b079aef785370f040f126cdb43d4e2a63a0da088d7e8e75943408764aa824"}
]

with httpx.Client(verify=False) as client:
    for p in payloads:
        r = client.post(url, headers=headers, json=p)
        print(f"PAYLOAD {p} -> [{r.status_code}] {r.text}")
