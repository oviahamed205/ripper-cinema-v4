"""
Dean Edwards P.A.C.K.E.R Unpacker for Ripper Resolver.
Pure-Python implementation supporting radix 10, 36, 62, and 95 encodings,
nested packed wrappers, and string lookup table substitution with zero external dependencies.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ALPHABET_62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALPHABET_95 = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
)


_PACKER_JUICERS = (
    re.compile(
        r"}\('(.*?)', *(\d+|\[\]), *(\d+), *'(.*?)'\.split\('\|'\), *(\d+), *(.*?)\)\)",
        re.DOTALL,
    ),
    re.compile(
        r"}\('(.*?)', *(\d+|\[\]), *(\d+), *'(.*?)'\.split\('\|'\)",
        re.DOTALL,
    ),
)


class Unbaser:
    """Functor to convert radix encoded string tokens into natural integers."""

    def __init__(self, radix: int) -> None:
        self.radix = radix
        if 2 <= radix <= 36:
            self._unbase: Callable[[str], int] = lambda s: int(s, radix)
        else:
            alphabet = ALPHABET_95[:radix] if radix > 62 else ALPHABET_62[:radix]
            self.char_map: Dict[str, int] = {char: idx for idx, char in enumerate(alphabet)}
            self._unbase = self._dict_unbase

    def _dict_unbase(self, token: str) -> int:
        ret = 0
        for char in token:
            val = self.char_map.get(char)
            if val is None or val >= self.radix:
                return -1
            ret = ret * self.radix + val
        return ret

    def __call__(self, token: str) -> int:
        try:
            return self._unbase(token)
        except Exception:
            return -1


def detect_packed(source: str) -> bool:
    """Determine if a JavaScript string contains Dean Edwards packed code."""
    if not source:
        return False
    return "eval(function(p,a,c,k,e," in source


def _replace_string_lookup_tables(source: str) -> str:
    """Resolve Obfuscator.io / legacy string arrays like var _0xabc=['a', 'b'] into their values."""
    match = re.search(r'var\s+(_\w+)\s*=\s*\["(.*?)"\];', source, re.DOTALL)
    if not match:
        match = re.search(r"var\s+(_\w+)\s*=\s*\['(.*?)'\];", source, re.DOTALL)

    if match:
        var_name, raw_strings = match.groups()
        delimiter = '","' if '","' in raw_strings else "','"
        lookup = raw_strings.split(delimiter)
        for idx, val in enumerate(lookup):
            source = source.replace(f"{var_name}[{idx}]", f'"{val}"')
    return source


def unpack_packer(source: str) -> str:
    """
    Unpack a Dean Edwards P.A.C.K.E.R. JavaScript block.
    Returns the decompressed JavaScript code string.
    """
    from .fast_accel import fast_unpack_dean_edwards
    try:
        return fast_unpack_dean_edwards(source)
    except Exception as exc:
        logger.debug("Fast acceleration path failed, running baseline unpacker: %s", exc)

    payload: Optional[str] = None
    symtab: Optional[List[str]] = None
    radix = 62
    count = 0

    for pattern in _PACKER_JUICERS:
        match = pattern.search(source)
        if match:
            groups = match.groups()
            radix_val = groups[1]
            radix = 62 if radix_val == "[]" else int(radix_val)
            count = int(groups[2])
            symtab = groups[3].split("|")
            payload = groups[0]
            break

    if payload is None or symtab is None:
        logger.debug("Failed to extract P.A.C.K.E.R parameters from source")
        return source

    unbaser = Unbaser(radix)

    def _lookup(m: re.Match) -> str:
        word = m.group(0)
        idx = unbaser(word)
        if 0 <= idx < len(symtab) and symtab[idx]:
            return symtab[idx]
        return word

    payload = payload.replace("\\\\", "\\").replace("\\'", "'")
    unpacked = re.sub(r"\b\w+\b", _lookup, payload)
    unpacked = _replace_string_lookup_tables(unpacked)

    # Recursive unpacking in case of nested packed scripts (up to 3 levels)
    if detect_packed(unpacked) and unpacked != source:
        return unpack_packer(unpacked)

    return unpacked
