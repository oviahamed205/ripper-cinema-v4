# 🛠️ RESOLVER CORE: ALGORITHMIC PRIMITIVES & DEOBFUSCATORS

---

## 1. Pure-HTTP reCAPTCHA v3 Anchor Negotiator (`ripper/resolver/core/recaptcha_v3.py`)

### Purpose
Bypasses invisible Google reCAPTCHA v3 gates without loading a browser engine or paying third-party CAPTCHA solving APIs.

### Algorithmic Execution Steps
1. **Fetch Anchor Token**:
   - Send HTTP GET to:
     `https://www.google.com/recaptcha/api2/anchor?ar=1&k={sitekey}&co={co_base64}&v={version}&size=invisible`
   - Extract the hidden `recaptcha-token` from response HTML:
     ```regex
     id="recaptcha-token"\s+value="([^"]+)"
     ```
2. **Reload & Obtain Challenge Solution**:
   - Send HTTP POST to:
     `https://www.google.com/recaptcha/api2/reload?k={sitekey}`
   - Form Payload: `v={version}&reason=q&c={recaptcha_token}&k={sitekey}&co={co_base64}`
3. **Parse Response Token**:
   - Extract `rresp` token via regex:
     ```regex
     "rresp","([^"]+)"
     ```
4. **Result**: Returns valid token in **< 100ms** to pass in subsequent form submissions.

---

## 2. Cryptographic Deobfuscators (`ripper/resolver/core/crypto_unpacker.py`)

### A. DealDose Algorithmic Cipher (`decode_dealdose_url`)
Used on portals such as `worldfree4u.gd`:
```python
def decode_dealdose_url(token: str) -> str:
    # 1. Reverse the obfuscated string
    reversed_str = token[::-1]
    
    # 2. Normalize Base64 URL-safe alphabet
    normalized = reversed_str.replace("-", "+").replace("_", "/").replace(",", "=")
    
    # 3. Add padding if needed
    pad_len = len(normalized) % 4
    if pad_len > 0:
        normalized += "=" * (4 - pad_len)
        
    # 4. Decode direct target URL
    return base64.b64decode(normalized.encode()).decode("utf-8", errors="ignore")
```

### B. Adfly `ysmm` Cipher (`decode_adfly_ysmm`)
Decodes the proprietary `ysmm` link cipher in `0ms`:
1. Split input into even-indexed characters `a` and odd-indexed characters `b` (in reverse order).
2. Rejoin `a + b`.
3. Iterate character pairs: if both are digits and XOR value \( < 10 \), replace with XOR result.
4. Slice inner range `[16:-16]` and Base64 decode to reveal the target link.

### C. BlueMediaFiles Midpoint Splicer (`decode_bluemedia_key`)
Extracts the encoded key from `Create_Button("...")`:
1. Identify midpoint `mid = len(key) // 2`.
2. Extract outbound slices `key[mid-5:mid]` and `key[mid:mid+4]`.
3. Construct request to `/get-url.php?url={spliced_key}`.

### D. Nested `atob()` De-wrapper (`decode_nested_atob`)
Recursively peels Base64 wrappers up to 4 layers deep until a valid URL scheme (`http://` or `https://`) is recovered.

---

## 3. JavaScript Unpackers (`ripper/resolver/core/js_unpacker.py`)

### A. Dean Edwards Packer (`unpack_dean_edwards`)
Matches scripts matching `eval(function(p,a,c,k,e,d)...)`:
- Parses payload `p`, base `a`, count `c`, and lookup dictionary `k`.
- Replaces encoded base-N tokens with original identifiers to reconstruct the raw JavaScript payload.

### B. Next.js SSR Hydration Parser (`parse_nextjs_data`)
- Finds `<script id="__NEXT_DATA__" type="application/json">`.
- Parses JSON tree: `props.pageProps.data` or `props.pageProps.downloadUrl`.

### C. SvelteKit SSR Extractor (`parse_sveltekit_json`)
- Parses SvelteKit hydration arrays (used by `links.kmhd.eu`) to extract direct download mirrors.

---

## 4. Honeypot Filter (`ripper/resolver/core/honeypot_filter.py`)

Eliminates fake buttons and malicious pop-under triggers:
- **CSS Hiding Check**: Discards elements containing:
  - `display:\s*none`
  - `visibility:\s*hidden`
  - `opacity:\s*0`
  - `position:\s*absolute;\s*left:\s*-\d+px`
- **Ad-Network Domain Blacklist**: Blocks known trap networks (Adsterra, PropellerAds, PopAds, ExoClick).

---

## 5. Binary-Safe HTTP Transport (`ripper/resolver/core/binary_safe_http.py`)

Protects system RAM from large media file downloads:
```python
async def request_capped(
    client, 
    method: str, 
    url: str, 
    max_bytes: int = 2 * 1024 * 1024, # 2MB Max
    **kwargs
) -> SafeResponse:
    # 1. Open streaming response
    async with client.stream(method, url, **kwargs) as resp:
        content_type = resp.headers.get("content-type", "").lower()
        
        # 2. Check MIME: Abort immediately if binary stream
        if any(m in content_type for m in ["video/", "application/zip", "application/octet-stream"]):
            return SafeResponse(status_code=resp.status_code, is_binary=True, final_url=str(resp.url))
            
        # 3. Read up to max_bytes only
        body = await resp.aread(max_bytes)
        return SafeResponse(status_code=resp.status_code, text=body.decode(errors="ignore"), final_url=str(resp.url))
```
