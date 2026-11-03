"""
AdFly / J.gs / Q.gs Algorithmic Bitwise Decryptor.
Solves Adf.ly and its 50+ alias domains (j.gs, q.gs, ay.gy, tinyium, etc.)
by extracting the 'ysmm' variable and executing the odd/even transposition and bitwise XOR key derivation.
"""

from __future__ import annotations

import base64
import re
import time
from urllib.parse import unquote, urlparse

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class AdFlySolver(BaseAdGateSolver):
    """Bypasses Adf.ly, J.gs, Q.gs, and related shorteners via mathematical ysmm decryption."""

    name: str = "adfly"

    SUPPORTED_DOMAINS = {
        "adf.ly", "j.gs", "q.gs", "ay.gy", "zo.ee", "babblecase.com", "riffhold.com",
        "microify.com", "pintient.com", "tinyium.com", "atominik.com", "bluenik.com",
        "atomcurve.com", "picocurl.com", "casualient.com", "simizer.com", "viahold.com",
        "kaitect.com", "yoalizer.com", "kibuilder.com", "quainator.com", "yobuilder.com",
        "vializer.com", "yabuilder.com", "activeation.com", "brisktopia.com", "zipteria.com",
        "agileurbia.com", "fasttory.com", "swifttopia.com", "clearload.bid", "brightvar.bid",
        "kudoflow.com", "turboagram.com", "streamvoyage.com", "metastead.com", "swarife.com",
        "cinebo.net", "uclaut.net", "linkup.pro", "gloyah.net", "fainbory.com", "onisedeo.com",
        "aclabink.com", "optitopt.com", "thacorag.com", "raboninco.com", "motriael.com",
        "fumacrom.com", "hurirk.net", "xervoo.net", "eloism.net", "uhishado.com", "lyksoomu.com"
    }

    @staticmethod
    def decrypt_ysmm(code: str) -> str:
        """
        Executes AdFly's odd-even character transposition and adjacent bitwise XOR key shuffle.
        """
        left, right = "", ""
        for i in range(len(code)):
            if i % 2 == 0:
                left += code[i]
            else:
                right = code[i] + right

        key = list(left + right)
        i = 0
        while i < len(key):
            if key[i].isdigit():
                for j in range(i + 1, len(key)):
                    if key[j].isdigit():
                        u = int(key[i]) ^ int(key[j])
                        if u < 10:
                            key[i] = str(u)
                        i = j
                        break
            i += 1

        shuffled_key = "".join(key)
        # Pad base64 if needed
        rem = len(shuffled_key) % 4
        if rem:
            shuffled_key += "=" * (4 - rem)

        decrypted = base64.b64decode(shuffled_key.encode("ascii"))
        # Strip padding slices [16:-16]
        if len(decrypted) > 32:
            decrypted = decrypted[16:-16]

        target = decrypted.decode("utf-8", errors="ignore")

        # Unwrap any go.php?u= wrapper
        if "go.php?u=" in target:
            raw_b64 = re.sub(r".*?u=", "", target)
            rem = len(raw_b64) % 4
            if rem:
                raw_b64 += "=" * (4 - rem)
            target = base64.b64decode(raw_b64.encode("ascii")).decode("utf-8", errors="ignore")
        elif "&dest=" in target:
            target = unquote(re.sub(r".*?dest=", "", target))

        return target

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                parsed = urlparse(str(resp.url))
                # Check if already redirected to final destination
                if not any(ad in parsed.netloc for ad in self.SUPPORTED_DOMAINS):
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        intermediate_urls=intermediates
                    )

                html = resp.text
                m = re.search(r'ysmm\s*=\s*[\'"]([^\'"]+)[\'"]', html)
                if m:
                    ysmm_code = m.group(1)
                    target = self.decrypt_ysmm(ysmm_code)
                    if target.startswith(("http://", "https://")):
                        intermediates.append(target)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=target,
                            gate_type=GateType.AD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used="adfly_ysmm_decrypt",
                            intermediate_urls=intermediates
                        )

        except Exception as e:
            return ShortlinkResult(
                original_url=url,
                resolved_url=None,
                gate_type=GateType.AD_GATE,
                success=False,
                duration=time.time() - start_time,
                solver_used=self.name,
                intermediate_urls=intermediates,
                error=str(e)
            )

        return ShortlinkResult(
            original_url=url,
            resolved_url=None,
            gate_type=GateType.AD_GATE,
            success=False,
            duration=time.time() - start_time,
            solver_used=self.name,
            intermediate_urls=intermediates,
            error="AdFly solver could not locate ysmm cryptographic key in page DOM"
        )
