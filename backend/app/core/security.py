"""API key encryption and decryption utilities for storing AI model API keys.

Production deployments MUST set `ENCRYPTION_KEY` to a Fernet key
(generate via `Fernet.generate_key().decode()`). When ENCRYPTION_KEY is a
raw Fernet key it's used directly; otherwise the value is stretched via
PBKDF2 with a long, application-specific salt so that a weak
SECRET_KEY-derived fallback is not the worst-case.

If neither ENCRYPTION_KEY nor a sufficiently strong SECRET_KEY is
available, encryption will still work in development (for convenience)
but `validate_for_runtime()` has already refused to boot in production.
"""
import base64
import logging
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.core.config import settings

log = logging.getLogger(__name__)

# Long, random, app-specific salt baked into the binary. Not a secret — its
# purpose is to prevent rainbow-table attacks against the KDF, not to hide.
_KDF_SALT = b"cc-security/v2/2026-04::api-key-storage::do-not-change"
_KDF_ITERATIONS = 200_000

# Legacy salt used before the strengthening pass; kept for transparent
# backward-compatible decryption of keys stored by earlier versions.
_LEGACY_KDF_SALT = b"cc-security-salt"
_LEGACY_KDF_ITERATIONS = 100_000


def _is_valid_fernet_key(value: str) -> bool:
    """A Fernet key is a URL-safe base64 encoding of exactly 32 bytes."""
    try:
        raw = base64.urlsafe_b64decode(value.encode())
    except Exception:
        return False
    return len(raw) == 32


def _derive_fernet() -> Fernet:
    """Build a Fernet instance from settings."""
    explicit = (settings.encryption_key or "").strip()
    if explicit and _is_valid_fernet_key(explicit):
        return Fernet(explicit.encode())

    source = (explicit or settings.secret_key or "change-me").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_KDF_SALT,
        iterations=_KDF_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(source))
    return Fernet(key)


def encrypt_api_key(plain: str) -> str:
    """Encrypt an API key."""
    return _derive_fernet().encrypt(plain.encode()).decode()


def _legacy_fernet() -> Fernet:
    """Fernet using the pre-strengthening salt/iterations. Decrypt-only."""
    source = ((settings.encryption_key or "").strip() or settings.secret_key or "change-me").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_LEGACY_KDF_SALT,
        iterations=_LEGACY_KDF_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(source))
    return Fernet(key)


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt an API key. Tries the current KDF, falls back to the legacy
    one for rows stored by earlier versions.

    Raises ValueError if neither works (key mismatch or tampering).
    """
    token = encrypted.encode()
    try:
        return _derive_fernet().decrypt(token).decode()
    except InvalidToken:
        pass
    try:
        return _legacy_fernet().decrypt(token).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Unable to decrypt stored API key. This usually means "
            "SECRET_KEY / ENCRYPTION_KEY has changed since the key was stored."
        ) from exc


def mask_api_key(plain: str) -> str:
    """Mask an API key for display (first 4 chars + **** + last 4 chars)."""
    if len(plain) <= 8:
        return "****"
    return plain[:4] + "****" + plain[-4:]
