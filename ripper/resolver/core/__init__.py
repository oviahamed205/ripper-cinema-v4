"""
Core Engine Primitives for Ripper Resolver.
Provides memory safety, pre-flight stream validation, circuit breaker,
honeypot filtration, and JavaScript / cryptographic deobfuscators.
"""
from __future__ import annotations

from .circuit_guard import (
    is_circuit_open,
    record_domain_failure,
    record_domain_success,
)
from .honeypot_filter import (
    AD_TRAP_DOMAINS,
    host_of,
    is_ad_trap,
    is_hidden_element,
)
from .crypto_unpacker import (
    _clean_extracted_url,
    _is_followable_http_url,
    decode_rot13,
    caesar_decipher,
    decode_multistage_caesar_b64,
    decode_xor_token,
    decode_base64_url,
    decode_bluemedia_key,
    decode_nested_atob,
    decrypt_adfly_ysmm,
    extract_shortener_api_url,
    decode_dealdose_url,
    extract_url_from_query_params,
    extract_embedded_b64_url,
    extract_embedded_hex_url,
    extract_embedded_encoded_url,
    extract_embedded_media_stream,
)

from .js_unpacker import (
    unpack_dean_edwards_packer,
    extract_meta_refresh_url,
    extract_js_redirect_url,
    parse_kmhd_sveltekit_data,
    parse_nextjs_data,
    unpack_obfuscator_io_hex_array,
)
from .packer_unpack import (
    unpack_packer,
    detect_packed,
)
from .doh_resolver import (
    resolve_doh,
    clear_doh_cache,
)
from .fast_accel import (
    fast_hash64,
    fast_compile,
    fast_unpack_dean_edwards,
    get_acceleration_status,
    is_native_rust_available,
    is_c_regex_available,
    is_xxhash_available,
)

from .binary_safe_http import (

    FetchResult,
    coerce_timeout,
    default_headers,
    normalize_start_url,
    is_direct_storage_url,
    is_direct_file_url,
    looks_like_html,
    looks_like_binary,
    extract_filename_from_url_or_headers,
    _guess_media_content_type,
    is_bot_challenge,
    request_capped,
    request_capped_with_client,
    fetch_with_impersonation,
    DEFAULT_USER_AGENT,
    DEFAULT_ACCEPT_HTML,
    DOWNLOAD_EXTENSIONS,
    VIDEO_EXTENSIONS,
    STORAGE_HOST_MARKERS,
    MAX_HTML_BYTES,
)
from .stream_validator import (
    validate_presigned_url,
    probe_mirror_latency,
    pick_fastest_live_mirror,
)
from .recaptcha_v3 import (
    solve_recaptcha_v3_anchor,
    solve_recaptcha_v3_anchor_sync,
)


__all__ = [
    "is_circuit_open",
    "record_domain_failure",
    "record_domain_success",
    "AD_TRAP_DOMAINS",
    "host_of",
    "is_ad_trap",
    "is_hidden_element",
    "_clean_extracted_url",
    "_is_followable_http_url",
    "decode_rot13",
    "caesar_decipher",
    "decode_multistage_caesar_b64",
    "decode_xor_token",
    "decode_base64_url",
    "decode_bluemedia_key",
    "decode_nested_atob",
    "decrypt_adfly_ysmm",
    "extract_shortener_api_url",
    "decode_dealdose_url",
    "extract_url_from_query_params",
    "extract_embedded_b64_url",
    "extract_embedded_hex_url",
    "extract_embedded_encoded_url",
    "extract_embedded_media_stream",
    "unpack_dean_edwards_packer",

    "extract_meta_refresh_url",
    "extract_js_redirect_url",
    "parse_kmhd_sveltekit_data",
    "parse_nextjs_data",
    "unpack_obfuscator_io_hex_array",
    "FetchResult",
    "coerce_timeout",
    "default_headers",
    "normalize_start_url",
    "is_direct_storage_url",
    "is_direct_file_url",
    "looks_like_html",
    "looks_like_binary",
    "extract_filename_from_url_or_headers",
    "_guess_media_content_type",
    "is_bot_challenge",
    "request_capped",
    "request_capped_with_client",
    "fetch_with_impersonation",
    "DEFAULT_USER_AGENT",
    "DEFAULT_ACCEPT_HTML",
    "DOWNLOAD_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "STORAGE_HOST_MARKERS",
    "MAX_HTML_BYTES",
    "validate_presigned_url",
    "probe_mirror_latency",
    "pick_fastest_live_mirror",
    "solve_recaptcha_v3_anchor",
    "solve_recaptcha_v3_anchor_sync",
    "fast_hash64",
    "fast_compile",
    "fast_unpack_dean_edwards",
    "get_acceleration_status",
    "is_native_rust_available",
    "is_c_regex_available",
    "is_xxhash_available",
]