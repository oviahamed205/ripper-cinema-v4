import os
import time
import re
from urllib.parse import urlparse, parse_qs
import json
import base64

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from curl_cffi import requests

import requests as std_requests

# 🔥 Website URL from .env
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://hdhub4u.catering").rstrip("/")

class HDHubBypass:
    def __init__(self):
        # Primary session (Standard requests) - Fast
        self.std_session = std_requests.Session()
        self.std_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # Fallback session (curl_cffi) - Initialized lazily
        self.curl_session = None

    def _get_curl_session(self):
        if not self.curl_session:
             self.curl_session = requests.Session()
             self.curl_session.impersonate = "chrome110"
             self.curl_session.headers = self.std_session.headers
        return self.curl_session

    def _get(self, url):
        # Optimization: Try persistent standard session first
        try:
            print(f"[*] Requesting: {url}")
            resp = self.std_session.get(url, timeout=10)

            if resp.status_code in [403, 503]:
                print(f"[*] Std requests got {resp.status_code}, switching to curl_cffi...")
                raise Exception("Cloudflare Block")

            return resp

        except Exception as e:
            # Fallback to curl_cffi
            # print(f"[*] Falling back to curl_cffi due to: {e}")
            return self._get_curl_session().get(url, timeout=30)


    def bypass(self, url):
        print(f"[*] Starting bypass for: {url}")

        # Step 1: GadgetsWeb (Initial Page)
        # The logs show a simple visit, then a click to /homelander/
        # But usually these sites have a timer or hidden form.
        # Let's verify the first page execution.


        # 🚨 SECURITY NOTICE 2: Behavior Analyis
        # This script sends requests instantly.
        # A secure site would track mouse movements (entropy) and click timing.
        # Since we send NO mouse data, a 'behavior' check would block us immediately here.
        try:
            resp = self._get(url)
            print(f"[*] GadgetsWeb Status: {resp.status_code}")

            # Debug: Save landing page
            with open("debug_landing.html", "w", encoding="utf-8") as f:
                f.write(resp.text)


            # Use regex to find the redirect or next step
            # Logs show next step is /homelander/
            if "/homelander/" not in resp.text and "homelander" not in resp.url and "/homelander/" not in url:
                 # Check for meta refresh or JS redirect?
                 # For now, let's assume we need to go to /homelander/ if we aren't there.
                 # Actually, logs show UserClick on "verify_btn" on /homelander/
                 pass

            # If the URL is already the final one or close to it, handle it.

            # Pattern from logs:
            # 1. https://gadgetsweb.xyz/?id=...
            # 2. https://gadgetsweb.xyz/homelander/

            if "gadgetsweb.xyz" in url:
                if "/homelander/" not in url:
                   # Try to infer if we need to post or just navigate
                   # Often these have a form.
                   pass

            # Let's follow the log flow strictly for now.
            # Log shows a visit to /homelander/ after the ID page.
            # Just visiting the ID page might set a cookie or session.

            # time.sleep(2) # Speed up: removed wait


            # Step 2: /homelander/
            homelander_url = "https://gadgetsweb.xyz/homelander/"
            print(f"[*] Navigating to: {homelander_url}")
            resp = self._get(homelander_url)

            # Step 2b: Automate the JS Decryption
            # Logic reversed: Token -> B64 -> B64 -> Rot13 -> B64 -> JSON -> 'o' -> B64 -> URL

            # We need the 'o' token from the LANDING page content (which we requested in Step 1)
            # We can't use the 'resp' from Step 2 (Homelander) because the token is in Step 1.
            # But in Step 1 we didn't save the response to a variable we can access here easily?
            # actually we did 'resp = self.session.get(url...)' at line 25.

            # We need to re-fetch or use the content if we still have it.
            # Let's assume we need to re-fetch if we didn't save it properly, but 'resp' variable is reused.
            # So let's re-fetch the Landing page to get the token, or better, store it in Step 1.

            # Refetching Landing Page to be sure
            print("[*] Parsing Landing Page for bypass token...")
            resp_landing = self._get(url)
            token_match = re.search(r"s\('o','([^']+)'", resp_landing.text)

            if token_match:
                token = token_match.group(1)
                print("[*] Found obfuscated token. Decrypting...")


                try:
                    # 🚨 SECURITY NOTICE 1: Client-Side Logic
                    # The site sends the encrypted token AND the logic to decrypt it (Rot13).
                    # This makes it trivial to reverse. A secure site would keep this logic
                    # on the server and only issue a session token.

                    # 1. Base64 Decode
                    s1 = base64.b64decode(token).decode('utf-8')
                    # 2. Base64 Decode
                    s2 = base64.b64decode(s1).decode('utf-8')

                    # 3. Rot13
                    def rot13(s):
                        res = []
                        for char in s:
                            if 'a' <= char <= 'z':
                                res.append(chr((ord(char) - ord('a') + 13) % 26 + ord('a')))
                            elif 'A' <= char <= 'Z':
                                res.append(chr((ord(char) - ord('A') + 13) % 26 + ord('A')))
                            else:
                                res.append(char)
                        return "".join(res)

                    s3 = rot13(s2)

                    # 4. Base64 Decode (Pad if needed)
                    # s3 might need padding
                    padded = s3 + "=" * ((4 - len(s3) % 4) % 4)
                    s4 = base64.b64decode(padded).decode('utf-8')

                    # 5. Parse JSON
                    data = json.loads(s4)
                    hubcloud_b64 = data.get('o')

                    if hubcloud_b64:
                        next_url = base64.b64decode(hubcloud_b64).decode('utf-8')
                        print(f"[*] DECRYPTED SUCCESS! HubCloud URL: {next_url}")
                    else:
                        print("[!] JSON decoded but 'o' key missing.")
                        return

                except Exception as e:
                    print(f"[!] Decryption failed: {e}")
                    return
            else:
                 print("[!] Could not find token in Landing Page.")
                 # Try finding manual fallback just in case? No, user said break it.
                 return
            # Step 4: HubCloud
            # Log: https://hubcloud.foo/drive/gosaa50wlwy24k3
            # Navigate there
            print(f"[*] Navigating to HubCloud: {next_url}")
            # time.sleep(1)

            resp = self._get(next_url)

            # Log shows UserClick on a#download.btn.btn-primary.h6.p-2
            # We need to find this link.
            # It likely points to carnewz.site

            carnewz_match = re.search(r'href="([^"]+)"[^>]*id="download"', resp.text)
            if not carnewz_match:
                 carnewz_match = re.search(r'href="([^"]+)"[^>]*carnewz\.site', resp.text)

            if carnewz_match:
                carnewz_url = carnewz_match.group(1) if "http" in carnewz_match.group(1) else carnewz_match.group(0) # varying regex groups
                # fix if regex matched full url in group 0 for second case
                if "href=" not in carnewz_match.group(0):
                     carnewz_url = carnewz_match.group(1)
                else:
                     # re-match for clean url if needed
                     pass

                # Let's keep it simple: find url in href
                pass

            # Try finding the #download button href specifically (Handle both id-first and href-first)
            carnewz_url = None
            # Case 1: id then href
            btn_match = re.search(r'<a[^>]*id="download"[^>]*href="([^"]+)"', resp.text)
            if btn_match:
                carnewz_url = btn_match.group(1)
            else:
                # Case 2: href then id
                btn_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*id="download"', resp.text)
                if btn_match:
                     carnewz_url = btn_match.group(1)

            if carnewz_url:
                print(f"[*] Found Download URL: {carnewz_url}")
                # Clean HTML entities
                carnewz_url = carnewz_url.replace("&amp;", "&")
            else:

                    print("[!] Could not find Carnewz URL.")
                    print(f"[*] DEBUG: HubCloud Page Content (First 1000 chars):\n{resp.text[:1000]}")
                    # Save for full inspection
                    with open("debug_hubcloud.html", "w", encoding="utf-8") as f:
                        f.write(resp.text)
                    return

            # Step 6: Final Destination
            # Visit Carnewz
            # time.sleep(1)

            # 🚨 SECURITY NOTICE 4: Short-Lived Tokens
            # If the token 'gosaa...' was bound to the User-Agent or IP and expired
            # in 3 seconds, this request might fail if we are too slow or IP rotates.
            resp = self._get(carnewz_url)

            # Log shows UserClick on #fsl.btn.btn-success
            # This usually means the final link is in that button.

            final_match = re.search(r'href="([^"]+)"[^>]*id="fsl"', resp.text)
            if final_match:
                final_link = final_match.group(1)
                print(f"[*] SUCCESS! Final Link: {final_link}")
                return final_link
            else:
                 # Try generic search for gdriv/gfile/other patterns if ID fails
                 print("[!] Could not find final link with id='fsl'")
                 print(f"[*] Debug: Page content snippet: {resp.text[:500]}...")

        except Exception as e:
            print(f"[!] Error: {e}")

    def run(self, start_url):
        # Step 0: Check if we are on the Movie Page or the Redirect Page (gadgetsweb)

        current_url = start_url
        if "gadgetsweb.xyz" not in current_url:
            print(f"[*] Analyzing Movie Page: {current_url}")
            try:
                # Use persistent session
                resp = self.std_session.get(current_url, timeout=30)

                # Find ALL gadgetsweb links (for fallback support)
                gw_links = re.findall(r'href="([^"]*gadgetsweb\.xyz[^"]*)"', resp.text)

                if not gw_links:
                    print("[!] No gadgetsweb links found. Trying broad search...")
                    gw_links = re.findall(r'href="([^"]*\?id=[a-zA-Z0-9%=]+)"', resp.text)

                if not gw_links:
                    print("[!] Could not find any download links on page.")
                    return

                # Remove duplicates while preserving order
                seen = set()
                unique_links = []
                for lnk in gw_links:
                    lnk_clean = lnk.replace("&amp;", "&")
                    if lnk_clean not in seen:
                        seen.add(lnk_clean)
                        unique_links.append(lnk_clean)

                print(f"[*] Found {len(unique_links)} download link(s). Trying with fallback...")

                # Try each link until one works
                for i, link in enumerate(unique_links):
                    print(f"\n[*] Attempting link {i+1}/{len(unique_links)}: {link[:60]}...")
                    try:
                        result = self.bypass(link)
                        if result:
                            return result
                        print(f"[!] Link {i+1} failed. Trying next...")
                    except Exception as e:
                        print(f"[!] Link {i+1} error: {e}. Trying next...")
                        continue

                print("[!] All links failed.")
                return None

            except Exception as e:
                print(f"[!] Error fetching movie page: {e}")
                return

        return self.bypass(current_url)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        start_url = sys.argv[1]
    else:
        # Default/Test
        start_url = f"{WEBSITE_URL}/love-through-a-prism-series-5331/"

    bypass = HDHubBypass()
    bypass.run(start_url)
