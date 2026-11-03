import httpx
import re
import time
import random
import string

filecode = 'f1jy0udr99xa'
mirrors = [
    f'https://doodstream.com/e/{filecode}',
    f'https://dood.to/e/{filecode}',
    f'https://dood.so/e/{filecode}',
    f'https://dood.la/e/{filecode}',
    f'https://dood.ws/e/{filecode}',
    f'https://dood.sh/e/{filecode}',
    f'https://d000d.com/e/{filecode}',
    f'https://d0000d.com/e/{filecode}',
    f'https://ds2play.com/e/{filecode}',
    f'https://dood.pm/e/{filecode}',
    f'https://dood.li/e/{filecode}',
    f'https://dood.re/e/{filecode}',
    f'https://dood.wf/e/{filecode}',
    f'https://dood.cx/e/{filecode}',
    f'https://dood.yt/e/{filecode}',
    f'https://dood.stream/e/{filecode}',
    f'https://dooodster.com/e/{filecode}',
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

with httpx.Client(verify=False, follow_redirects=True, timeout=8.0) as client:
    for m_url in mirrors:
        try:
            r = client.get(m_url, headers=headers)
            print(f'[{r.status_code}] {m_url} -> {r.url}')
            m_pass = re.search(r'/pass_md5/([^"\']+)', r.text)
            if m_pass:
                print(f'   ✔ FOUND pass_md5 on {r.url}: {m_pass.group(1)}')
                # Test resolving pass_md5
                pass_url = f"https://{r.url.netloc}/pass_md5/{m_pass.group(1)}"
                p_resp = client.get(pass_url, headers={'Referer': str(r.url), 'User-Agent': headers['User-Agent']})
                print(f'   ✔ PASS_MD5 BODY: {p_resp.text}')
                rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                ts = int(time.time() * 1000)
                final_direct_url = f"{p_resp.text}{rand_str}?token={m_pass.group(1)}&expiry={ts}"
                print(f'   🔥 FINAL DIRECT MP4: {final_direct_url}')
                # Test direct MP4 head request
                mp4_head = client.head(final_direct_url, headers={'Referer': f'https://{r.url.netloc}/', 'User-Agent': headers['User-Agent']})
                print(f'   🎯 DIRECT MP4 HEAD STATUS: {mp4_head.status_code} ({mp4_head.headers.get("content-length")} bytes)')
                break
        except Exception as e:
            print(f'   ❌ {m_url}: {e}')
