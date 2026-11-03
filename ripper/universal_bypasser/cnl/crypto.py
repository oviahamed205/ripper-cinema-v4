"""
Click'n'Load 2 (CNL2) AES-128-CBC Decryptor.
Evaluates the 'jk' key generator function and decrypts AES-128-CBC encrypted payloads
into clean, newline-delimited hoster URLs.
"""

from __future__ import annotations

import base64
import re
from typing import List

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class CNL2Crypto:
    """Handles evaluation of CNL key expressions and AES-128-CBC link decryption."""

    @staticmethod
    def extract_key_from_jk(jk_str: str) -> bytes:
        """
        Parses and evaluates the Click'n'Load 'jk' JavaScript snippet.
        Matches common return forms such as:
        - function f(){ return "31323334353637383930313233343536"; }
        - return 'abcdef0123456789abcdef0123456789'
        """
        if not jk_str:
            raise ValueError("Empty jk key generator string")

        # Match direct hex return: return "0123456789abcdef...";
        m = re.search(r"return\s*['\"]([0-9a-fA-F]{32})['\"]", jk_str)
        if m:
            return bytes.fromhex(m.group(1))

        # Match variable assignment and return: var k = "0123..."; return k;
        m = re.search(r"['\"]([0-9a-fA-F]{32})['\"]", jk_str)
        if m:
            return bytes.fromhex(m.group(1))

        # Match ASCII key return
        m = re.search(r"return\s*['\"]([^'\"]{16})['\"]", jk_str)
        if m:
            return m.group(1).encode("utf-8")

        # Fallback: find any 16-byte ascii string or 32-char hex string
        m = re.search(r"['\"]([^'\"]{16})['\"]", jk_str)
        if m:
            return m.group(1).encode("utf-8")

        raise ValueError(f"Unable to extract 16-byte AES key from jk script: {jk_str[:100]}")

    @classmethod
    def decrypt(cls, crypted_b64: str, jk_str: str) -> List[str]:
        """
        Decrypts a CNL2 crypted payload using key derived from jk.
        Returns a list of clean URLs.
        """
        key = cls.extract_key_from_jk(jk_str)
        iv = key  # In standard Click'n'Load specification, IV is identical to Key

        # Decode base64 payload
        ciphertext = base64.b64decode(crypted_b64.replace(" ", "+").strip())

        # Setup AES-128-CBC
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        # Unpad (strip null bytes and PKCS#7 padding)
        pad_len = plaintext[-1]
        if 1 <= pad_len <= 16:
            # Check if valid PKCS7 padding
            if plaintext[-pad_len:] == bytes([pad_len] * pad_len):
                plaintext = plaintext[:-pad_len]

        # Strip any trailing null bytes
        plaintext = plaintext.rstrip(b"\x00")

        # Decode UTF-8 and split URLs by newline
        decoded_text = plaintext.decode("utf-8", errors="replace")
        urls = [line.strip() for line in decoded_text.splitlines() if line.strip().startswith(("http://", "https://"))]
        return urls
