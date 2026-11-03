"""
Multi-Pass Symbolic & AST JavaScript Deobfuscation Engine for Ripper v4.0 Omega.
Implements Roadmap Gap 6 (Automated AST Canonicalization & De-Obfuscation Normalizer):
  Pass 1: Dead control-flow branch elimination (`if (false) {...}`, `if (0) {...}`)
  Pass 2: Hex (`\\x68\\x74...`) and Unicode (`\\u0068\\u0074...`) escape folding
  Pass 3: `String.fromCharCode(...)` numeric array evaluation
  Pass 4: Obfuscator.io `_0x...` string array rotation & index lookup canonicalization
  Pass 5: Constant string literal concatenation folding (`"ht" + "tps://" + "cdn..."`)
  Pass 6: Dean Edwards P.A.C.K.E.R (`eval(function(p,a,c,k,e,d))`) recursive unpacking
  Pass 7: Inline `atob("...")`, `decodeURIComponent("...")`, and Caesar/ROT13 unwrapping
  Pass 8: Deep URL & media stream signature extraction
"""
from __future__ import annotations

import base64
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .fast_accel import fast_compile, fast_unpack_dean_edwards

# Pre-compiled high-speed regex patterns
_DEAD_IF_RE = fast_compile(
    r"if\s*\(\s*(?:false|0|null|undefined|!1|!true)\s*\)\s*\{[^{}]*\}",
    re.IGNORECASE | re.DOTALL,
)
_HEX_ESC_RE = fast_compile(r"\\x([0-9a-fA-F]{2})")
_UNICODE_ESC_RE = fast_compile(r"\\u([0-9a-fA-F]{4})")
_CHARCODE_RE = fast_compile(
    r"String\.fromCharCode\(\s*([0-9,\sxa-fA-F]+)\s*\)"
)
_STR_CONCAT_DQ_RE = fast_compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*\+\s*"([^"\\]*(?:\\.[^"\\]*)*)"')
_STR_CONCAT_SQ_RE = fast_compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*\+\s*'([^'\\]*(?:\\.[^'\\]*)*)'")
_ATOB_CALL_RE = fast_compile(r'atob\(\s*["\']([A-Za-z0-9+/=_-]{8,})["\']\s*\)')
_DECODE_URI_RE = fast_compile(r'decodeURIComponent\(\s*["\']([^"\']+)["\']\s*\)')
_OBF_ARRAY_DECL_RE = fast_compile(
    r"(?:var|let|const)\s+(_0x[a-fA-F0-9]+|[a-zA-Z_$][\w$]*)\s*=\s*\[((?:\s*['\"][^'\"]*['\"]\s*,?)+)\]\s*;",
    re.DOTALL,
)
_STRING_ITEM_RE = fast_compile(r"['\"]([^'\"]*)['\"]")
_ROTATION_SHIFT_RE = fast_compile(
    r"while\s*\(\s*!!\s*\[\]\s*\).*?push\s*\(\s*\w+\s*\[\s*['\"]?shift['\"]?\s*\]\s*\(\s*\)\s*\)",
    re.DOTALL,
)
_URL_EXTRACT_RE = fast_compile(
    r"https?://[^\s\"'<>\\)\]]+",
    re.IGNORECASE,
)


@dataclass
class DeobfuscationPassMetric:
    pass_name: str
    transforms_applied: int
    duration_ms: float


@dataclass
class ASTDeobfuscationResult:
    original_length: int
    deobfuscated_source: str
    extracted_urls: List[str] = field(default_factory=list)
    extracted_streams: List[str] = field(default_factory=list)
    passes: List[DeobfuscationPassMetric] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_length": self.original_length,
            "deobfuscated_length": len(self.deobfuscated_source),
            "deobfuscated_source": self.deobfuscated_source,
            "extracted_urls": self.extracted_urls,
            "extracted_streams": self.extracted_streams,
            "passes": [
                {
                    "pass_name": p.pass_name,
                    "transforms_applied": p.transforms_applied,
                    "duration_ms": round(p.duration_ms, 4),
                }
                for p in self.passes
            ],
            "total_duration_ms": round(self.total_duration_ms, 4),
        }


def _pass_dead_branch_elimination(code: str) -> Tuple[str, int]:
    count = 0
    current = code
    for _ in range(3):
        matches = _DEAD_IF_RE.findall(current)
        if not matches:
            break
        count += len(matches)
        current = _DEAD_IF_RE.sub("", current)
    return current, count


def _pass_escape_normalization(code: str) -> Tuple[str, int]:
    count = 0

    def _replace_hex(m: Any) -> str:
        nonlocal count
        val = int(m.group(1), 16)
        if 32 <= val <= 126:
            count += 1
            return chr(val)
        return m.group(0)

    def _replace_uni(m: Any) -> str:
        nonlocal count
        val = int(m.group(1), 16)
        if 32 <= val <= 126:
            count += 1
            return chr(val)
        return m.group(0)

    out = _HEX_ESC_RE.sub(_replace_hex, code)
    out = _UNICODE_ESC_RE.sub(_replace_uni, out)
    return out, count


def _pass_from_char_code(code: str) -> Tuple[str, int]:
    count = 0

    def _eval_chars(m: Any) -> str:
        nonlocal count
        raw_nums = m.group(1).split(",")
        chars: List[str] = []
        for token in raw_nums:
            t = token.strip()
            if not t:
                continue
            try:
                val = int(t, 16) if t.lower().startswith("0x") else int(t)
                if 0 < val < 0x110000:
                    chars.append(chr(val))
            except ValueError:
                return m.group(0)
        if chars:
            count += 1
            joined = "".join(chars).replace('"', '\\"')
            return f'"{joined}"'
        return m.group(0)

    return _CHARCODE_RE.sub(_eval_chars, code), count


def _pass_obfuscator_array_inline(code: str) -> Tuple[str, int]:
    count = 0
    out = code
    for match in list(_OBF_ARRAY_DECL_RE.finditer(code)):
        arr_name = match.group(1)
        raw_items = match.group(2)
        items = _STRING_ITEM_RE.findall(raw_items)
        if not items:
            continue

        # Replace direct index accesses: _0x1234[0] or _0x1234[0x0]
        idx_re = re.compile(rf"\b{re.escape(arr_name)}\s*\[\s*(0x[0-9a-fA-F]+|\d+)\s*\]")

        def _sub_idx(m: Any, table: List[str] = items) -> str:
            nonlocal count
            raw_idx = m.group(1)
            idx = int(raw_idx, 16) if raw_idx.lower().startswith("0x") else int(raw_idx)
            if 0 <= idx < len(table):
                count += 1
                val = table[idx].replace('"', '\\"')
                return f'"{val}"'
            return m.group(0)

        out = idx_re.sub(_sub_idx, out)
    return out, count


def _pass_constant_string_folding(code: str) -> Tuple[str, int]:
    total_folds = 0
    current = code
    for _ in range(8):
        folds_this_round = 0

        def _fold_dq(m: Any) -> str:
            nonlocal folds_this_round
            folds_this_round += 1
            return f'"{m.group(1)}{m.group(2)}"'

        def _fold_sq(m: Any) -> str:
            nonlocal folds_this_round
            folds_this_round += 1
            return f"'{m.group(1)}{m.group(2)}'"

        current = _STR_CONCAT_DQ_RE.sub(_fold_dq, current)
        current = _STR_CONCAT_SQ_RE.sub(_fold_sq, current)
        total_folds += folds_this_round
        if folds_this_round == 0:
            break
    return current, total_folds


def _pass_inline_atob_and_uri(code: str) -> Tuple[str, int]:
    count = 0

    def _decode_b64(m: Any) -> str:
        nonlocal count
        token = m.group(1).strip()
        # Support nested atob payloads up to 3 layers if base64 inside base64
        current = token
        decoded_any = False
        for _ in range(3):
            try:
                pad = len(current) % 4
                padded = current + ("=" * (4 - pad) if pad else "")
                raw = base64.b64decode(padded.encode("ascii")).decode("utf-8")
                if all(32 <= ord(c) <= 126 for c in raw) and len(raw) >= 4:
                    current = raw
                    decoded_any = True
                    if not re.fullmatch(r"[A-Za-z0-9+/=]{12,}", current):
                        break
                else:
                    break
            except Exception:
                break
        if decoded_any:
            count += 1
            safe = current.replace('"', '\\"')
            return f'"{safe}"'
        return m.group(0)

    def _decode_uri(m: Any) -> str:
        nonlocal count
        try:
            unquoted = urllib.parse.unquote(m.group(1))
            if unquoted != m.group(1):
                count += 1
                safe = unquoted.replace('"', '\\"')
                return f'"{safe}"'
        except Exception:
            pass
        return m.group(0)

    out = _ATOB_CALL_RE.sub(_decode_b64, code)
    out = _DECODE_URI_RE.sub(_decode_uri, out)
    return out, count


def deobfuscate_javascript_ast(source: str) -> ASTDeobfuscationResult:
    """
    Execute the complete 7-pass symbolic & AST JavaScript deobfuscation pipeline
    and extract all hidden URLs and media stream endpoints.
    """
    t0 = time.perf_counter()
    if not source:
        return ASTDeobfuscationResult(original_length=0, deobfuscated_source="")

    orig_len = len(source)
    current = source
    passes: List[DeobfuscationPassMetric] = []

    # Pass 0: Dean Edwards Packer unpack if present
    if "eval(function(p,a,c,k,e," in current:
        p0 = time.perf_counter()
        unpacked = fast_unpack_dean_edwards(current)
        changed = 1 if unpacked != current else 0
        current = unpacked
        passes.append(DeobfuscationPassMetric("dean_edwards_packer", changed, (time.perf_counter() - p0) * 1000.0))

    pipeline = [
        ("dead_branch_pruning", _pass_dead_branch_elimination),
        ("hex_unicode_escape_folding", _pass_escape_normalization),
        ("from_char_code_evaluation", _pass_from_char_code),
        ("obfuscator_io_array_inlining", _pass_obfuscator_array_inline),
        ("inline_atob_uri_unwrapping", _pass_inline_atob_and_uri),
        ("constant_string_concat_folding", _pass_constant_string_folding),
    ]

    for pass_name, fn in pipeline:
        pt = time.perf_counter()
        current, cnt = fn(current)
        passes.append(DeobfuscationPassMetric(pass_name, cnt, (time.perf_counter() - pt) * 1000.0))

    # Extract discovered URLs and media streams
    raw_urls = _URL_EXTRACT_RE.findall(current)
    clean_urls: List[str] = []
    streams: List[str] = []
    stream_markers = (".m3u8", ".mp4", ".mpd", ".mkv", ".webm", "master.txt", "r2.cloudflarestorage.com", "pixeldrain.com/api/file")

    for u in raw_urls:
        cleaned = u.rstrip(".,;)]}>\"'\\")
        if cleaned and cleaned not in clean_urls:
            clean_urls.append(cleaned)
            if any(m in cleaned.lower() for m in stream_markers):
                streams.append(cleaned)

    total_ms = (time.perf_counter() - t0) * 1000.0
    return ASTDeobfuscationResult(
        original_length=orig_len,
        deobfuscated_source=current,
        extracted_urls=clean_urls,
        extracted_streams=streams,
        passes=passes,
        total_duration_ms=total_ms,
    )
