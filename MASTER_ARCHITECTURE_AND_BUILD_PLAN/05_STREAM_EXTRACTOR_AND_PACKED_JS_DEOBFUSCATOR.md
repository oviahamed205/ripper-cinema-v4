# 🔓 STREAM EXTRACTOR & PACKED JS DEOBFUSCATOR
### Dean Edwards Unpacker, Base64/XOR Decoders, and Video Cloud Host Extractors

---

## 1. Supported Cloud Video Host Drivers

The **Stream Extractor Engine (`unshorten/resolver.py`)** extracts raw MP4 / M3U8 video streams from all major hosting services:

```
┌─────────────────────────────────────────────────────────────┐
│                 Direct Stream Resolvers                     │
├─────────────────┬─────────────────┬─────────────────────────┤
│ HubCloud / Voe  │ FastCloud / Vid │ StreamTape / FileLions  │
│ GDToT / KatDrive│ DoodStream / Mix│ PixelDrain / 1Fichier   │
└─────────────────┴─────────────────┴─────────────────────────┘
```

---

## 2. Dean Edwards `eval(p,a,c,k,e,d)` Unpacker Algorithm

Many streaming hosts obfuscate stream links using the classic packed JavaScript format:
```javascript
eval(function(p,a,c,k,e,d){e=function(c){return...};...}('0 1=2.3("4");...',5,5,'var|stream_url|document|getElementById|my_video'.split('|'),0,{}))
```

### Pure-Python Unpacker Logic:
```python
import re

def unbase(val_str: str, base: int) -> int:
    digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    res = 0
    for char in val_str:
        res = res * base + digits.index(char)
    return res

def unpack_dean_edwards(packed_js: str) -> str:
    """Unpacks eval(p,a,c,k,e,d) packed javascript in pure Python without browser runtime."""
    match = re.search(r"}\s*\('(.*)',\s*(\d+),\s*(\d+),\s*'(.*?)'\.split\('\|'\)", packed_js, re.DOTALL)
    if not match:
        return packed_js

    payload, radix, count, symtab_raw = match.groups()
    radix = int(radix)
    symtab = symtab_raw.split("|")

    def lookup(word_match):
        token = word_match.group(0)
        idx = unbase(token, radix)
        return symtab[idx] if idx < len(symtab) and symtab[idx] else token

    unpacked = re.sub(r"\b[0-9a-zA-Z]+\b", lookup, payload)
    return unpacked
```

---

## 3. Anti-Hotlinking Headers Handshake

Cloud video hosts protect against direct downloading by validating request headers:
* `Referer`: Must match the initial embed player parent URL (e.g. `https://hubcloud.club/`).
* `User-Agent`: Must match the client user-agent string used during token generation.
* `Range`: Required for video players (PotPlayer, VLC) to stream partial byte buffers.

When returning resolved URLs, the engine outputs a **Pipe-Delimited Stream URI**:
```
https://cdn14.hubcloud.club/stream/video.mp4|Referer=https://hubcloud.club/&User-Agent=Mozilla/5.0...
```
PotPlayer and VLC natively parse this pipe format to pass authentic HTTP headers during playback!
