import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import urllib.parse
import re

with open("script13.js", "r", encoding="utf-8") as f:
    js_text = f.read()

m = re.search(r'decodeURI\("([^"]+)"\)', js_text)
if m:
    raw_encoded = m.group(1)
    raw_t = urllib.parse.unquote(raw_encoded).replace("@@", "@")
    res = []
    for n_idx, char in enumerate(raw_t):
        r = ord(char) - 32
        if 0 <= r < 95:
            res.append(chr(32 + (r + n_idx) % 95))
        else:
            res.append(char)
    decoded_t = "".join(res)
    print("DECODED T FULL:")
    print(decoded_t)
