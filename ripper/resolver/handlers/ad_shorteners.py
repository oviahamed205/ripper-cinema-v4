"""
Ad-Gate & Timer Bypasser Handler (GPLinks, Droplink, Ouo, Shorte, BlueMediaFiles, Shareus, etc.).
Bypasses intermediate countdown timers, submits virtual CSRF forms, and extracts destination payloads.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core.crypto_unpacker import (
    decode_bluemedia_key,
    decrypt_adfly_ysmm,
    extract_shortener_api_url,
    decode_multistage_caesar_b64,
    _clean_extracted_url,
    _is_followable_http_url,
)
from ..core.recaptcha_v3 import solve_recaptcha_v3_anchor
from ...models import HopInfo

logger = logging.getLogger(__name__)

SHORTENER_DOMAINS = (
    "gplinks.co", "gplinks.in", "gplinks.com", "droplink.co", "droplinks.in",
    "ouo.io", "ouo.press", "shorte.st", "sh.st", "adfly", "adf.ly", "ay.gy",
    "tinyurl.com", "bit.ly", "is.gd", "t.co", "rocklinks.net", "linkvertise.com",
    "bluemediafiles.com", "bluemediafiles.net", "bluemediafile.site",
    "shareus.io", "shortingly.in", "shortingly.me", "tnlink.in", "ez4short.com",
    "short2url.in", "gyanilinks.com", "try2link.com", "techyuth.xyz",
    "vnshortener.com", "modsfire.com", "keeplinks.org", "1shortlink.com", "1short.io", "linkbox.to",
    "linkjust.com", "pahe.plus", "go.zovo.ink", "shortnest.com", "vglist.top", "vglist.nl",
    "gtlinks.me", "theforyou.in", "pkin.me", "paisakamalo.in", "sirigan.my.id",
    "desbloquea.me", "drivelinks.me", "acortame-esto.com", "recorta-enlace.com", "enlace-protegido.com",
    "mobilejsr.com",
)



class AdShortenersHandler(BaseResolverHandler):
    name = "ad_shorteners"
    priority = 30

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if "/full?api=" in low or "/st?api=" in low:
            return True
        if any(d in low for d in SHORTENER_DOMAINS):
            return True
        if html and any(sig in html.lower() for sig in (
            "gplinks", "droplink", "rocklinks", "adlinkfly", "bluemedia", "shareus", "go-link", "ysmm", "sessionid"
        )):
            return True
        return False

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops: List[HopInfo] = []
        try:
            # 1. Check Full-Page / Quick-Link API unwrapping
            api_unwrapped = extract_shortener_api_url(url)
            if api_unwrapped:
                hops.append(make_hop(url=api_unwrapped, status_code=200, redirect_type="shortener_api_unwrap", extra_details="Unwrapped from shortener full/quick API"))
                return api_unwrapped, hops

            # 2. Check direct query unwrapping
            parsed = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed.query)
            for param in ("url", "dest", "destination", "target", "link", "goto", "redirect"):
                if param in query_params:
                    val = query_params[param][0]
                    if val.startswith("http"):
                        hops.append(make_hop(url=val, status_code=200, redirect_type="query_param_unwrap", extra_details=f"Extracted from ?{param}="))
                        return val, hops
                    try:
                        decoded = base64.b64decode(val).decode("utf-8", errors="ignore")
                        if decoded.startswith("http"):
                            hops.append(make_hop(url=decoded, status_code=200, redirect_type="base64_query_unwrap", extra_details="Decoded Base64 destination parameter"))
                            return decoded, hops
                    except Exception as exc:
                        logger.debug("Base64 query param decode error: %s", exc)

            # 3. Check Linkvertise ?r= easy base64 parameter
            if "linkvertise.com" in url.lower() and "r=" in url:
                r_val = query_params.get("r", [""])[0]
                if r_val:
                    try:
                        r_dec = base64.b64decode(urllib.parse.unquote(r_val)).decode("utf-8", errors="ignore").strip()
                        if _is_followable_http_url(r_dec):
                            hops.append(make_hop(url=r_dec, status_code=200, redirect_type="linkvertise_r_param", extra_details="Decoded Linkvertise ?r= destination"))
                            return r_dec, hops
                    except Exception as exc:
                        logger.debug("Linkvertise r-param decode error: %s", exc)

            # 4. Check Ouo.io / Ouo.press reCAPTCHA v3 flow
            if "ouo.io" in url.lower() or "ouo.press" in url.lower():
                ouo_res = await self._resolve_ouo(url, client, context, hops)
                if ouo_res:
                    return ouo_res, hops

            # 5. Check GPLinks 2-stage flow
            if "gplinks" in url.lower():
                gp_res = await self._resolve_gplinks(url, client, context, hops)
                if gp_res:
                    return gp_res, hops

            # 6. Check specialized Shareus cloudfunction flow
            if "shareus.io" in url.lower():
                shareus_res = await self._resolve_shareus(url, client, context, hops)
                if shareus_res:
                    return shareus_res, hops

            # 7. Check VnShortener 2-stage ID flow
            if "vnshortener.com" in url.lower():
                vn_res = await self._resolve_vnshortener(url, client, context, hops)
                if vn_res:
                    return vn_res, hops

            # 8. Check Try2Link 4-minute token and go-link submission
            if "try2link.com" in url.lower():
                try_res = await self._resolve_try2link(url, client, context, hops)
                if try_res:
                    return try_res, hops

            # 9. Check GTLinks / TheForYou token gateway
            if any(d in url.lower() for d in ("gtlinks.me", "theforyou.in", "kinemaster.cc")):
                gt_res = await self._resolve_gtlinks(url, client, context, hops)
                if gt_res:
                    return gt_res, hops

            # 10. Check Pkin.me / Paisakamalo gateway
            if any(d in url.lower() for d in ("pkin.me", "paisakamalo.in")):
                pkin_res = await self._resolve_pkin(url, client, context, hops)
                if pkin_res:
                    return pkin_res, hops

            # 11. Check Multi-Stage Caesar/Base64 gateways (desbloquea, drivelinks, acortame-esto)
            if any(d in url.lower() for d in ("desbloquea.me", "drivelinks.me", "acortame-esto.com", "recorta-enlace.com", "enlace-protegido.com")):
                caesar_res = decode_multistage_caesar_b64(url)
                if caesar_res:
                    hops.append(make_hop(url=caesar_res, status_code=200, redirect_type="multistage_caesar_b64", extra_details="Decoded multi-stage Caesar + Base64 gateway"))
                    return caesar_res, hops

            # 12. Check Sirigan recursive base64 token
            if "sirigan.my.id" in url.lower():
                sirigan_res = await self._resolve_sirigan(url, client, context, hops)
                if sirigan_res:
                    return sirigan_res, hops

            # 13. Check MobileJSR cdn-cgi link
            if "mobilejsr.com" in url.lower():
                mjsr_resp = await client.get(url, headers=context.extra_headers, timeout=context.timeout)
                mjsr_text = getattr(mjsr_resp, "text", "")
                m_cgi = re.search(r'href=["\x27](https?://mobilejsr\.com/cdn-cgi/content\?[^"\x27]+)["\x27]', mjsr_text)
                if m_cgi:
                    target_url = m_cgi.group(1)
                    hops.append(make_hop(url=target_url, status_code=getattr(mjsr_resp, "status_code", 200), redirect_type="mobilejsr_cgi", extra_details="Extracted MobileJSR cdn-cgi link"))
                    return target_url, hops

            # 14. Fetch gateway landing

            resp = await client.get(url, headers=context.extra_headers, timeout=context.timeout)
            html = getattr(resp, "text", "")
            status = getattr(resp, "status_code", 200)

            # Check HTTP 3xx Location header redirect (e.g. TinyURL, Bitly, t.co)
            headers = getattr(resp, "headers", {})
            if status in (301, 302, 303, 307, 308) and "location" in headers:
                loc = headers["location"].strip()
                full_loc = urllib.parse.urljoin(url, loc)
                hops.append(make_hop(url=full_loc, status_code=status, redirect_type="http_3xx", extra_details=f"Shortener 3xx Location redirect to {full_loc}"))
                return full_loc, hops

            hops.append(make_hop(url=url, status_code=status, redirect_type="ad_shortener_landing", extra_details=f"Ad-gate landing fetched (status {status})"))

            # 7. Check Adfly / AdF.ly ysmm variable decryptor
            if "ysmm" in html or "adfly" in url.lower() or "adf.ly" in url.lower() or "ay.gy" in url.lower():
                adfly_res = self._resolve_adfly(url, html, hops)
                if adfly_res:
                    return adfly_res, hops

            # 8. Check Shorte.st adsession handshake
            if "shorte.st" in url.lower() or "sh.st" in url.lower() or "sessionId" in html:
                shorte_res = await self._resolve_shorte(url, html, client, context, hops)
                if shorte_res:
                    return shorte_res, hops

            # 9. Check BlueMediaFiles Create_Button key decode
            if "bluemedia" in url.lower() or "Create_Button(" in html:
                bm_res = await self._resolve_bluemedia(url, html, client, context, hops)
                if bm_res:
                    return bm_res, hops

            # 10. Check Multi-Step Form Automation (/links/go)
            form_res = await self._resolve_form_links_go(url, html, client, context, hops)
            if form_res:
                return form_res, hops

            # 11. Check inline timer destination script token
            match_go = re.search(r'var\s+app_url\s*=\s*["\x27](https?://[^"\x27]+)["\x27]', html)
            if match_go:
                target = match_go.group(1)
                hops.append(make_hop(url=target, status_code=status, redirect_type="ad_script_token", extra_details="Extracted timer script destination"))
                return target, hops

            # 7. Check DOM anchors for skip/continue links
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True).lower()
                if "get link" in text or "continue" in text or "skip ad" in text:
                    if href.startswith("http") and not any(d in href for d in SHORTENER_DOMAINS):
                        hops.append(make_hop(url=href, status_code=status, redirect_type="get_link_anchor", extra_details="Extracted Get Link button destination"))
                        return href, hops

        except Exception as exc:
            hops.append(make_hop(url=url, status_code=0, redirect_type="shortener_error", extra_details=f"Shortener error: {exc}"))

        return None

    async def _resolve_bluemedia(
        self,
        url: str,
        html: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Decode BlueMediaFiles Create_Button key and fetch direct target."""
        try:
            btn_match = re.search(r'Create_Button\(["\x27]([^"\x27]+)["\x27]\)', html)
            if not btn_match:
                return None
            encoded_key = btn_match.group(1)
            decoded_key = decode_bluemedia_key(encoded_key)
            if not decoded_key:
                return None

            api_url = f"https://bluemediafiles.com/get-url.php?url={urllib.parse.quote(decoded_key)}"
            headers = dict(context.extra_headers)
            headers["Referer"] = url

            bm_resp = await client.get(api_url, headers=headers, timeout=context.timeout)
            final_url = str(getattr(bm_resp, "url", api_url))

            # Handle MEGA link format in BlueMediaFiles
            if "mega.nz" in final_url:
                final_url = final_url.replace("mega.nz/%23!", "mega.nz/file/").replace("!", "#")

            hops.append(make_hop(
                url=final_url,
                status_code=getattr(bm_resp, "status_code", 200),
                redirect_type="bluemedia_key_decoded",
                extra_details=f"Decoded key length: {len(decoded_key)}",
            ))
            return final_url
        except Exception:
            return None

    async def _resolve_shareus(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Walk Shareus cloudfunction pagination to retrieve destination."""
        try:
            code = url.rstrip("/").split("/")[-1]
            if not code:
                return None
            domain = "https://us-central1-my-apps-server.cloudfunctions.net"
            headers = dict(context.extra_headers)
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

            init_url = f"{domain}/v?shortid={code}&initial=true&referrer=https://shareus.io/"
            await client.get(init_url, headers=headers, timeout=context.timeout)

            for page in range(1, 4):
                try:
                    await client.post(f"{domain}/v", json={"current_page": page}, headers=headers, timeout=context.timeout)
                except Exception:
                    break

            link_resp = await client.get(f"{domain}/get_link", headers=headers, timeout=context.timeout)
            data = link_resp.json()
            if isinstance(data, dict) and "link_info" in data and "destination" in data["link_info"]:
                target = data["link_info"]["destination"]
                hops.append(make_hop(
                    url=target,
                    status_code=200,
                    redirect_type="shareus_cloudfunction",
                    extra_details="Traversed Shareus 3-page state",
                ))
                return target
        except Exception as exc:
            logger.debug("Failed in _resolve_shareus: %s", exc)
        return None

    async def _resolve_form_links_go(
        self,
        url: str,
        html: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract hidden form inputs and POST to /links/go with XMLHttpRequest headers."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            form = soup.find("form", id="go-link") or soup.find("form", action=re.compile(r"/links/go"))
            if not form:
                # Check for forms containing CSRF or token fields
                for f in soup.find_all("form"):
                    if f.find("input", attrs={"name": re.compile(r"csrf|token|ad_form", re.I)}):
                        form = f
                        break
            if not form:
                return None

            form_data: Dict[str, str] = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if name:
                    form_data[name] = inp.get("value", "")

            parsed = urllib.parse.urlparse(url)
            action = form.get("action", "")
            if action and action.startswith("http"):
                target_action = action
            elif action:
                target_action = urllib.parse.urljoin(url, action)
            else:
                target_action = f"{parsed.scheme}://{parsed.netloc}/links/go"

            post_headers = dict(context.extra_headers)
            post_headers.update({
                "X-Requested-With": "XMLHttpRequest",
                "Origin": f"{parsed.scheme}://{parsed.netloc}",
                "Referer": url,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            })

            post_resp = await client.post(target_action, data=form_data, headers=post_headers, timeout=context.timeout)
            if getattr(post_resp, "status_code", 0) in (200, 302):
                try:
                    data = post_resp.json()
                    if isinstance(data, dict) and "url" in data and _is_followable_http_url(data["url"]):
                        dest_url = _clean_extracted_url(data["url"])
                        hops.append(make_hop(
                            url=dest_url,
                            status_code=200,
                            redirect_type="links_go_form_post",
                            extra_details=f"Posted form to {target_action}",
                        ))
                        return dest_url
                except Exception as exc:
                    logger.debug("Failed parsing response from form target action: %s", exc)
        except Exception as exc:
            logger.debug("Failed executing _resolve_form_links_go: %s", exc)
        return None

    async def _resolve_shorte(
        self,
        url: str,
        html: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Resolve Shorte.st adsession by extracting sessionId and pinging end-adsession API."""
        try:
            sess_match = re.search(r"""sessionId\s*[:=]\s*['"](.*?)['"]""", html, re.I)
            if not sess_match:
                return None
            sess_id = sess_match.group(1)
            parsed = urllib.parse.urlparse(url)
            end_url = f"{parsed.scheme}://{parsed.netloc}/shortest-url/end-adsession"
            headers = dict(context.extra_headers)
            headers["Referer"] = url
            headers["Accept"] = "application/json"

            resp = await client.get(
                end_url,
                params={"adSessionId": sess_id, "callback": "_"},
                headers=headers,
                timeout=context.timeout,
            )
            # Try JSON extraction first
            try:
                data = resp.json() if hasattr(resp, "json") else {}
                if isinstance(data, dict):
                    for k in ("destination", "url", "target"):
                        if k in data and _is_followable_http_url(str(data[k])):
                            dest = _clean_extracted_url(str(data[k]))
                            hops.append(make_hop(
                                url=dest,
                                status_code=200,
                                redirect_type="shorte_adsession",
                                extra_details=f"Resolved Shorte.st adsession: {sess_id}",
                            ))
                            return dest
            except Exception as exc:
                logger.debug("Shorte.st JSON decode error: %s", exc)

            # Fallback to regex
            text = getattr(resp, "text", "")
            matches = re.findall(r'"(https?:[^\s"\'<>]+)"', text)
            if matches:
                target = _clean_extracted_url(matches[0].replace(r"\/", "/"))
                if _is_followable_http_url(target):
                    hops.append(make_hop(
                        url=target,
                        status_code=200,
                        redirect_type="shorte_adsession",
                        extra_details=f"Resolved Shorte.st adsession: {sess_id}",
                    ))
                    return target
        except Exception as exc:
            logger.debug("Shorte.st session error: %s", exc)
        return None

    async def _resolve_vnshortener(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Automate VnShortener 2-stage ID registration and form post."""
        try:
            parsed = urllib.parse.urlparse(url)
            code = parsed.path.strip("/").split("/")[0]
            domain = f"{parsed.scheme}://{parsed.netloc}"
            php_acc = f"{domain}/link/new.php"
            headers = dict(context.extra_headers)
            headers.update({"Origin": domain, "X-Requested-With": "XMLHttpRequest"})

            resp1 = await client.post(php_acc, data={"step_1": code}, headers=headers, timeout=context.timeout)
            data1 = resp1.json() if hasattr(resp1, "json") else {}
            inserted_id = (data1.get("inserted_data") or {}).get("id") or data1.get("id")
            if not inserted_id:
                return None

            await client.post(php_acc, data={"step_2": code, "id": inserted_id}, headers=headers, timeout=context.timeout)

            step_url = f"{domain}/{code}/"
            final_landing = await client.get(step_url, params={"sid": str(inserted_id)}, headers=headers, timeout=context.timeout)
            return await self._resolve_form_links_go(step_url, getattr(final_landing, "text", ""), client, context, hops)
        except Exception as exc:
            logger.debug("VnShortener error: %s", exc)
        return None

    def _resolve_adfly(self, url: str, html: str, hops: List[HopInfo]) -> Optional[str]:
        """Extract ysmm variable and decrypt Adfly destination."""
        try:
            match = re.search(r"""ysmm\s*=\s*['"](.*?)['"]""", html)
            if not match:
                return None
            ysmm_val = match.group(1)
            dest = decrypt_adfly_ysmm(ysmm_val)
            if dest:
                hops.append(make_hop(
                    url=dest,
                    status_code=200,
                    redirect_type="adfly_ysmm_decrypted",
                    extra_details="Decrypted Adfly ysmm token",
                ))
                return dest
        except Exception as exc:
            logger.debug("Adfly error: %s", exc)
        return None

    async def _resolve_ouo(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Resolve ouo.io and ouo.press shortlinks with automated reCAPTCHA v3 anchor handshake."""
        try:
            temp_url = url.replace("ouo.press", "ouo.io")
            parsed = urllib.parse.urlparse(temp_url)
            code = parsed.path.strip("/").split("/")[-1]
            if not code:
                return None

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://ouo.io/",
            }
            res = await client.get(temp_url, headers=headers, follow_redirects=False, timeout=context.timeout)
            loc = res.headers.get("Location") or res.headers.get("location")
            if loc and _is_followable_http_url(loc) and "ouo.io" not in loc and "ouo.press" not in loc:
                hops.append(make_hop(
                    url=loc,
                    status_code=302,
                    redirect_type="ouo_direct_redirect",
                    extra_details=f"Direct Location redirect: {code}",
                ))
                return loc

            html = getattr(res, "text", "")
            next_url = f"{parsed.scheme}://{parsed.netloc}/go/{code}"

            for step in range(2):
                soup = BeautifulSoup(html, "html.parser")
                inputs = soup.find_all("input", {"name": re.compile(r"token$")})
                if not inputs:
                    break
                data = {inp.get("name"): inp.get("value") for inp in inputs}

                # Solve reCAPTCHA v3 token via Google anchor handshake
                anchor_url = (
                    "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6Lcr1ncUAAAAAH3cghg6cOTPGARa8adOf-y9zv2x&"
                    "co=aHR0cHM6Ly9vdW8uaW86NDQz&hl=en&v=pCoGBhjs9s8EhFOHJFe8cqis&size=invisible&cb=ahgyd1gkfkhe"
                )
                token_ans = await solve_recaptcha_v3_anchor(anchor_url, client=client, timeout=context.timeout)
                if token_ans:
                    data["x-token"] = token_ans

                post_headers = {**headers, "Content-Type": "application/x-www-form-urlencoded"}
                resp_step = await client.post(
                    next_url,
                    data=data,
                    headers=post_headers,
                    follow_redirects=False,
                    timeout=context.timeout,
                )

                step_loc = resp_step.headers.get("Location") or resp_step.headers.get("location")
                if step_loc and _is_followable_http_url(step_loc) and "ouo.io" not in step_loc and "ouo.press" not in step_loc:
                    hops.append(make_hop(
                        url=step_loc,
                        status_code=302,
                        redirect_type="ouo_recaptcha_bypassed",
                        extra_details=f"Ouo.io bypassed in step {step + 1}",
                    ))
                    return step_loc

                html = getattr(resp_step, "text", "")
                next_url = f"{parsed.scheme}://{parsed.netloc}/xreallcygo/{code}"

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Ouo.io resolution failed: %s", exc)
        return None

    async def _resolve_gplinks(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Resolve gplinks.co / gplinks.in 2-stage redirect and #go-link AJAX form."""
        try:
            clean_url = url.rstrip("/")
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://mynewsmedia.co/",
            }
            # Initial probe for ?{vid}
            res = await client.get(clean_url, headers=headers, follow_redirects=False, timeout=context.timeout)
            loc = res.headers.get("Location") or res.headers.get("location") or ""
            target_url = clean_url
            if "=" in loc:
                vid = loc.split("=")[-1]
                target_url = f"{clean_url}/?{vid}"

            page = await client.get(target_url, headers=headers, timeout=context.timeout)
            html = getattr(page, "text", "")
            return await self._resolve_form_links_go(target_url, html, client, context, hops)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("GPLinks resolution failed: %s", exc)
        return None

    async def _resolve_try2link(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Bypass try2link with 4-minute time offset parameter and #go-link submission."""
        try:
            import time
            clean_url = url.rstrip("/")
            params = {"d": str(int(time.time()) + 240)}
            headers = {
                "Referer": "https://newforex.online/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            resp = await client.get(clean_url, params=params, headers=headers, timeout=context.timeout)
            html = getattr(resp, "text", "")
            if not html:
                return None
            soup = BeautifulSoup(html, "html.parser")
            go_link = soup.find(id="go-link")
            if not go_link:
                return None
            post_data = {}
            for inp in go_link.find_all("input"):
                name = inp.get("name")
                val = inp.get("value", "")
                if name:
                    post_data[name] = val
            post_headers = {
                "Host": "try2link.com",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://try2link.com",
                "Referer": clean_url,
                "User-Agent": headers["User-Agent"],
            }
            post_resp = await client.post("https://try2link.com/links/go", headers=post_headers, data=post_data, timeout=context.timeout)
            data = post_resp.json() if hasattr(post_resp, "json") else {}
            res_url = data.get("url")
            if res_url and _is_followable_http_url(res_url):
                direct = _clean_extracted_url(res_url)
                hops.append(make_hop(url=direct, status_code=200, redirect_type="try2link_direct", extra_details="Try2link target resolved via virtual form"))
                return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Try2link resolution failed: %s", exc)
        return None

    async def _resolve_gtlinks(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Resolve GTLinks / theforyou.in token gateway."""
        try:
            clean_url = url.rstrip("/")
            if "theforyou.in" in clean_url or "kinemaster.cc" in clean_url:
                token = clean_url.split("=")[-1]
            else:
                resp = await client.get(clean_url, timeout=context.timeout)
                target_loc = getattr(resp, "url", clean_url)
                token = str(target_loc).split("=")[-1]
            if not token:
                return None
            domain = "https://go.theforyou.in/"
            req_url = f"{domain}{token}"
            headers = {
                "Referer": "https://theforyou.in/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            resp2 = await client.get(req_url, headers=headers, timeout=context.timeout)
            html = getattr(resp2, "text", "")
            return await self._resolve_form_links_go(domain, html, client, context, hops)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("GTLinks resolution failed: %s", exc)
        return None

    async def _resolve_pkin(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Resolve Pkin.me / Paisakamalo gateway."""
        try:
            clean_url = url.rstrip("/")
            token = clean_url.split("/")[-1]
            domain = "https://go.paisakamalo.in/"
            headers = {
                "Referer": "https://techkeshri.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 11) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
                ),
            }
            resp = await client.get(f"{domain}{token}", headers=headers, timeout=context.timeout)
            html = getattr(resp, "text", "")
            return await self._resolve_form_links_go(domain, html, client, context, hops)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Pkin resolution failed: %s", exc)
        return None

    async def _resolve_sirigan(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Resolve Sirigan recursive base64 token."""
        try:
            resp = await client.get(url, timeout=context.timeout)
            loc = str(getattr(resp, "url", url))
            if "=" in loc:
                token = loc.split("=", 1)[-1]
                dec = token
                for _ in range(5):
                    try:
                        missing = len(dec) % 4
                        if missing:
                            dec += "=" * (4 - missing)
                        cand = base64.b64decode(dec).decode("utf-8", errors="ignore").strip()
                        if not cand:
                            break
                        dec = cand
                    except Exception:
                        break
                if "url=" in dec:
                    final_target = _clean_extracted_url(dec.split("url=")[-1].strip())
                    if _is_followable_http_url(final_target):
                        hops.append(make_hop(url=final_target, status_code=200, redirect_type="sirigan_direct", extra_details="Sirigan recursive base64 token unwrapped"))
                        return final_target
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Sirigan resolution failed: %s", exc)
        return None
