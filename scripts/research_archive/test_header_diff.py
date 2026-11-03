from curl_cffi import requests

url = "https://wesa331.bestblogexist.com/hls/hJ5ZnmCQFwQvd2bGUKFGiLyLNQ7mG4fL/master.txt"

# 1. Clean browser headers
s = requests.Session(impersonate="chrome120")
h1 = {"Referer": "https://playmate.to/"}
r1 = s.get(url, headers=h1)
print("CLEAN HEADERS STATUS:", r1.status_code)

# 2. With X-Forwarded-For
h2 = {"Referer": "https://playmate.to/", "CF-Connecting-IP": "113.21.230.163"}
r2 = s.get(url, headers=h2)
print("WITH CF-CONNECTING-IP STATUS:", r2.status_code)
