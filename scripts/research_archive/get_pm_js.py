import httpx
import re

url = "https://playmate.to/assets/js/player-core.min.js"
r = httpx.get(url, verify=False)
js = r.text

# Let's find string table and rotation function in player-core.min.js
print("JS Length:", len(js))
with open("playmate_core.js", "w", encoding="utf-8") as f:
    f.write(js)

print("Saved playmate_core.js")
