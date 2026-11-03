"""
ripper.resolver.core.decrypt_lcg
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cryptographic deobfuscator for 3-layer encrypted media sources (MegaCloud, Rabbit, Vidwish).
Ported from lobster/aniwatch decryptSrc2:
- Linear Congruential Generator (LCG) PRNG seed derivation: (seed * 1103515245 + 12345) & 0x7fffffff
- Multi-iteration reverse seed character shifting across printable ASCII (32-126)
- Reverse columnar transposition cipher
- Reverse Fisher-Yates character substitution array
"""

import base64
from typing import List, Dict, Optional


import re

def atob(data: str) -> str:
    """Decode base64 string handling URL-safe and standard base64 variants."""
    try:
        clean = data.strip()
        if not clean or not re.match(r'^[A-Za-z0-9+/=_-]+$', clean):
            return ""
        pad = (4 - len(clean) % 4) % 4
        clean += "=" * pad
        try:
            decoded_bytes = base64.b64decode(clean, validate=True)
        except Exception:
            decoded_bytes = base64.urlsafe_b64decode(clean)
        return decoded_bytes.decode("latin1")
    except Exception:
        return ""


def keygen2(megacloud_key: str, client_key: str) -> str:
    """
    Generate unified cryptographic key from MegaCloud key and dynamic client key.
    """
    result = []
    max_len = max(len(megacloud_key), len(client_key))
    for i in range(max_len):
        if i < len(megacloud_key):
            result.append(megacloud_key[i])
        if i < len(client_key):
            result.append(client_key[i])
    return "".join(result)


def seed_shuffle2(char_array: List[str], key: str) -> List[str]:
    """
    Generate permutation of char_array via deterministic seeded Fisher-Yates shuffle.
    """
    result = list(char_array)
    # Compute 32-bit hash
    hash_val = 0
    mask32 = 0xFFFFFFFF
    for ch in key:
        hash_val = (hash_val * 31 + ord(ch)) & mask32
    seed = hash_val

    def seed_rand(arg: int) -> int:
        nonlocal seed
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        return seed % arg if arg > 0 else 0

    n = len(result)
    for i in range(n - 1, 0, -1):
        j = seed_rand(i + 1)
        result[i], result[j] = result[j], result[i]

    return result


def columnar_cipher2(dec_src: str, key: str) -> str:
    """
    Reverse columnar transposition cipher on input string using key length as column count.
    """
    num_cols = len(key)
    if num_cols <= 0:
        return dec_src

    num_rows = (len(dec_src) + num_cols - 1) // num_cols
    col_lengths = [0] * num_cols

    # Calculate column lengths
    full_cols = len(dec_src) % num_cols
    for i in range(num_cols):
        col_lengths[i] = num_rows if (full_cols == 0 or i < full_cols) else num_rows - 1

    # Read columns from dec_src
    cols: List[str] = []
    idx = 0
    for i in range(num_cols):
        length = col_lengths[i]
        cols.append(dec_src[idx : idx + length])
        idx += length

    # Reconstruct row by row
    out: List[str] = []
    for r in range(num_rows):
        for c in range(num_cols):
            if r < len(cols[c]):
                out.append(cols[c][r])

    return "".join(out)


def reverse_layer(dec_src: str, gen_key: str, iteration: int, char_array: List[str]) -> str:
    """
    Reverse one layer of the 3-layer encryption.
    """
    layer_key = f"{gen_key}{iteration}"

    # Compute 32-bit hash seed
    hash_val = 0
    mask32 = 0xFFFFFFFF
    for ch in layer_key:
        hash_val = (hash_val * 31 + ord(ch)) & mask32
    seed = hash_val

    def seed_rand(arg: int) -> int:
        nonlocal seed
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        return seed % arg if arg > 0 else 0

    char_index: Dict[str, int] = {c: i for i, c in enumerate(char_array)}

    # 1. Reverse seed shift
    shifted: List[str] = []
    for ch in dec_src:
        if ch in char_index:
            c_idx = char_index[ch]
            rand_num = seed_rand(95)
            new_idx = (c_idx - rand_num + 95) % 95
            shifted.append(char_array[new_idx])
        else:
            shifted.append(ch)

    dec_src = "".join(shifted)

    # 2. Reverse columnar transposition cipher
    dec_src = columnar_cipher2(dec_src, layer_key)

    # 3. Generate substitution array via Fisher-Yates shuffle
    sub_values = seed_shuffle2(char_array, layer_key)
    char_map: Dict[str, str] = {sub_values[i]: char_array[i] for i in range(len(sub_values))}

    # 4. Reverse substitution mapping
    return "".join(char_map.get(ch, ch) for ch in dec_src)


def decrypt_src_2(src: str, client_key: str, megacloud_key: str) -> str:
    """
    Perform 3-layer decryption on encrypted media source string.
    Returns decrypted payload string (typically JSON or stream URL).
    """
    if not src:
        return ""

    layers = 3
    gen_key = keygen2(megacloud_key, client_key)

    # Base64 decode
    dec_src = atob(src)
    if not dec_src:
        return ""

    # Printable ASCII 32-126
    char_array = [chr(32 + i) for i in range(95)]

    # Reverse each layer from 3 down to 1
    for iteration in range(layers, 0, -1):
        dec_src = reverse_layer(dec_src, gen_key, iteration, char_array)

    # First 4 chars are length prefix
    if len(dec_src) < 4:
        return ""

    try:
        data_len = int(dec_src[:4])
        if data_len <= 0 or 4 + data_len > len(dec_src):
            return ""
        return dec_src[4 : 4 + data_len]
    except ValueError:
        return ""
