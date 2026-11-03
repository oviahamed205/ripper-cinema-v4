"""
Safety and security threat heuristics for unshorten-cli.
"""

import re
import urllib.parse
from typing import List, Tuple, Optional
from .models import SafetyReport

# High risk or suspicious extensions
EXECUTABLE_EXTENSIONS = {".exe", ".msi", ".bat", ".cmd", ".scr", ".vbs", ".js", ".hta", ".pif", ".wsf", ".cpl"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bin", ".dmg", ".pkg", ".apk"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".txt"}
MEDIA_EXTENSIONS = {".mkv", ".mp4", ".avi", ".webm", ".ts", ".m4v", ".mov", ".flv", ".mp3", ".flac", ".wav"}

# Direct Cloud & CDN Storage domains
CLOUD_STORAGE_DOMAINS = {
    "r2.cloudflarestorage.com",
    "amazonaws.com",
    "storage.googleapis.com",
    "blob.core.windows.net",
    "wasabisys.com",
    "backblazeb2.com",
    "digitaloceanspaces.com",
}

# Suspicious / common deceptive patterns
IP_REGEX = re.compile(r"^https?://(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?:/.*)?$", re.IGNORECASE)
SUSPICIOUS_TLDS = {".top", ".xyz", ".club", ".work", ".click", ".link", ".gq", ".tk", ".ml", ".cf", ".ga", ".rest", ".buzz", ".cam"}


def detect_mime_category(url: str, content_type: str) -> str:
    """Categorize the resource based on Content-Type, URL path, and cloud storage domains."""
    ct = (content_type or "").lower()
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    # Check Cloud Storage / CDN presigned streams
    if any(csd in domain for csd in CLOUD_STORAGE_DOMAINS):
        return "CLOUD_STORAGE"

    # Check extension
    for ext in EXECUTABLE_EXTENSIONS:
        if path.endswith(ext):
            return "EXECUTABLE"
    for ext in ARCHIVE_EXTENSIONS:
        if path.endswith(ext):
            return "ARCHIVE"
    for ext in MEDIA_EXTENSIONS:
        if path.endswith(ext):
            return "MEDIA"
    for ext in DOCUMENT_EXTENSIONS:
        if path.endswith(ext):
            return "DOCUMENT"

    # Check query parameters for filename clues (e.g. filename=...mkv)
    if "filename=" in parsed.query.lower():
        if any(f".{ext.lstrip('.')}" in parsed.query.lower() for ext in MEDIA_EXTENSIONS):
            return "MEDIA"
        if any(f".{ext.lstrip('.')}" in parsed.query.lower() for ext in ARCHIVE_EXTENSIONS):
            return "ARCHIVE"

    # Check MIME content-type
    if "video/" in ct or "audio/" in ct:
        return "MEDIA"
    if "application/x-msdownload" in ct or "application/x-executable" in ct or "application/octet-stream" in ct:
        return "EXECUTABLE" if any(path.endswith(e) for e in EXECUTABLE_EXTENSIONS) else "ARCHIVE"
    if "text/html" in ct or "application/xhtml" in ct:
        return "WEBPAGE"
    if "application/pdf" in ct:
        return "DOCUMENT"
    if "image/" in ct:
        return "MEDIA"
    if "application/zip" in ct or "application/x-rar" in ct or "application/x-7z" in ct:
        return "ARCHIVE"

    return "WEBPAGE" if not path or path.endswith("/") else "UNKNOWN"


def analyze_destination_safety(
    final_url: str,
    content_type: str = "",
    content_length: int = 0,
    total_hops: int = 0,
    ip_address: str = "",
    challenge_note: Optional[str] = None,
) -> SafetyReport:
    """Evaluate destination URL and calculate security risk score (0-100)."""
    flags: List[str] = []
    risk_score = 0

    parsed = urllib.parse.urlparse(final_url)
    domain = parsed.netloc.lower()
    is_https = (parsed.scheme.lower() == "https")

    # 1. Check Protocol Security
    if not is_https:
        flags.append("Insecure plain HTTP connection (No SSL/TLS encryption)")
        risk_score += 25

    # 2. Check Bot Challenge
    if challenge_note:
        flags.append(f"🛡️ Protected by Anti-Bot Wall: {challenge_note}")
        risk_score += 10

    # 3. Check Raw IP Hostnames
    if IP_REGEX.match(final_url):
        flags.append("Direct IP address used instead of valid domain name")
        risk_score += 35

    # 3. Check Suspicious TLDs
    if not any(csd in domain for csd in CLOUD_STORAGE_DOMAINS):
        for tld in SUSPICIOUS_TLDS:
            if domain.endswith(tld):
                flags.append(f"High-abuse top-level domain detected ({tld})")
                risk_score += 15
                break

    # 4. Check Content Category & File Risks
    mime_category = detect_mime_category(final_url, content_type)
    if mime_category == "EXECUTABLE":
        flags.append("⚠️ Final destination points to a downloadable EXECUTABLE (.exe / installer)")
        risk_score += 30
    elif mime_category == "ARCHIVE":
        flags.append("📦 Final destination points to a compressed archive / container file")
        risk_score += 5
    elif mime_category == "CLOUD_STORAGE":
        flags.append("☁️ Direct High-Speed Cloud Storage / Presigned CDN Stream (R2 / S3)")
        risk_score = 0

    # 5. Excessive Redirect Hops
    if total_hops > 8:
        flags.append(f"Excessive redirect chain ({total_hops} hops detected)")
        risk_score += 15

    # 6. Embedded credentials or suspicious @ in URL
    if "@" in parsed.netloc:
        flags.append("Suspicious user-info / @ symbol present in URL authority")
        risk_score += 40

    # Determine risk level
    risk_score = min(100, risk_score)
    if risk_score >= 50:
        risk_level = "HIGH RISK"
    elif risk_score >= 30:
        risk_level = "SUSPICIOUS"
    elif risk_score >= 15:
        risk_level = "LOW RISK"
    else:
        risk_level = "SAFE"

    return SafetyReport(
        domain=domain,
        is_https=is_https,
        risk_score=risk_score,
        risk_level=risk_level,
        mime_category=mime_category,
        content_type=content_type,
        content_length_bytes=content_length,
        flags=flags,
        ip_address=ip_address,
    )
