"""Safe file upload / download helpers.

Centralises three concerns that have historically been inconsistent across
upload endpoints:

1. **Filename sanitisation** — the original name is only kept for display;
   disk names are random UUIDs (callers already do this), but the preserved
   `original_filename` still needs to be stripped of path separators, control
   chars, and limited in length.
2. **Extension whitelist** — per-context allow-lists prevent users from
   uploading `.html`, `.svg`, `.exe` etc. as a "document".
3. **Safe path resolution** — before returning a file via `FileResponse`,
   resolve the target and assert it stays within the configured storage root.
   Guards against `../` / symlink escapes.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import unicodedata
from urllib.parse import urlparse
from fastapi import HTTPException
from app.core.config import settings


# ── Extension allow-lists per upload context ─────────────────────────────

ALLOWED_EXT_DOCUMENT = {".pdf", ".doc", ".docx", ".txt", ".md"}
ALLOWED_EXT_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_EXT_VIDEO = {".mp4", ".mov", ".avi"}

ALLOWED_EXT_TOE_FILE = ALLOWED_EXT_DOCUMENT | ALLOWED_EXT_IMAGE | ALLOWED_EXT_VIDEO
ALLOWED_EXT_ST_REFERENCE = {".pdf", ".doc", ".docx"}
ALLOWED_EXT_SFR_LIBRARY = {".csv", ".txt"}


# ── Filename sanitisation ────────────────────────────────────────────────

_BAD_NAME_RE = re.compile(r"[\x00-\x1f\x7f/\\]+")
_MAX_ORIGINAL_FILENAME_LEN = 255


def sanitize_filename(name: str | None) -> str:
    """Return a safe version of the user-supplied filename.

    - NFKC-normalise
    - strip path separators and control chars
    - collapse dots, spaces, and slashes that could trick parsers
    - bound to 255 chars
    """
    if not name:
        return "unnamed"
    # Normalise unicode; remove directory components if present
    name = unicodedata.normalize("NFKC", name)
    name = os.path.basename(name.replace("\\", "/"))
    name = _BAD_NAME_RE.sub("_", name).strip(" .")
    if not name:
        return "unnamed"
    if len(name) > _MAX_ORIGINAL_FILENAME_LEN:
        stem, ext = os.path.splitext(name)
        keep = _MAX_ORIGINAL_FILENAME_LEN - len(ext)
        name = stem[: max(1, keep)] + ext
    return name


def get_safe_extension(name: str | None, allowed: set[str]) -> str:
    """Return the lower-cased extension if it is in the allow-list; else raise HTTPException."""
    ext = os.path.splitext(name or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(
            400,
            f"File extension '{ext or '(none)'}' is not allowed. "
            f"Permitted: {', '.join(sorted(allowed))}",
        )
    return ext


def validate_size(content_len: int) -> None:
    """Raise if the payload exceeds the configured max upload size."""
    if content_len > settings.upload_max_bytes:
        raise HTTPException(
            400,
            f"File exceeds the size limit ({settings.max_upload_size_mb}MB)",
        )


# ── Safe path resolution ─────────────────────────────────────────────────


def _resolve_storage_root() -> str:
    return os.path.realpath(os.path.abspath(settings.storage_path))


def is_within_storage(file_path: str) -> bool:
    """True iff `file_path` resolves inside the configured storage directory.

    Follows symlinks via realpath, so a symlink inside storage that points
    out of the tree is also rejected.
    """
    if not file_path:
        return False
    try:
        root = _resolve_storage_root()
        target = os.path.realpath(os.path.abspath(file_path))
    except Exception:
        return False
    try:
        common = os.path.commonpath([root, target])
    except ValueError:
        # different drives on Windows
        return False
    return common == root


def assert_within_storage(file_path: str) -> None:
    """Raise 404 if the path escapes the storage root (don't leak the reason)."""
    if not is_within_storage(file_path):
        raise HTTPException(404, "File not found")


# ── SSRF protection for user-supplied URLs ───────────────────────────────

# Private / reserved IP ranges that must never be reached via user input.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:127.0.0.0/104"),
    ipaddress.ip_network("::ffff:10.0.0.0/104"),
    ipaddress.ip_network("::ffff:172.16.0.0/108"),
    ipaddress.ip_network("::ffff:192.168.0.0/112"),
    ipaddress.ip_network("::ffff:169.254.0.0/112"),
]


def _is_private_ip(host: str) -> bool:
    """Check whether *host* (IP literal or hostname) resolves to a blocked range."""
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass
    # Hostname — resolve and check every returned address.
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False  # unresolvable is handled elsewhere
    for info in infos:
        ip_str = info[4][0]
        try:
            if any(ipaddress.ip_address(ip_str) in net for net in _BLOCKED_NETWORKS):
                return True
        except ValueError:
            continue
    return False


def validate_ai_api_base(url: str) -> str:
    """Validate a user-supplied AI model ``api_base`` URL.

    Raises :class:`HTTPException` (400) when the URL scheme is non-HTTPS/HTTP
    or when the host resolves to a private / internal IP range (SSRF guard).

    Returns the cleaned URL on success.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        raise HTTPException(400, "api_base URL is required")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "api_base must use http or https scheme")

    host = parsed.hostname or ""
    if not host:
        raise HTTPException(400, "api_base must contain a valid hostname")

    if _is_private_ip(host):
        raise HTTPException(
            400,
            "api_base must not point to a private or internal network address",
        )

    return url
