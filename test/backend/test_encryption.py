"""Tests for the API-key encryption helpers, including backward
compatibility with keys encrypted under the legacy (pre-strengthening) KDF."""
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core import security as sec_module
from app.core.config import settings


def test_encrypt_decrypt_roundtrip():
    token = sec_module.encrypt_api_key("sk-supersecret")
    assert token != "sk-supersecret"
    assert sec_module.decrypt_api_key(token) == "sk-supersecret"


def test_mask_api_key():
    assert sec_module.mask_api_key("sk-abcdefghij12345") == "sk-a****2345"
    assert sec_module.mask_api_key("short") == "****"


def test_wrong_key_raises():
    token = sec_module.encrypt_api_key("payload")
    # Flip the first data char after the version byte — Fernet will reject.
    bad = token[:10] + ("B" if token[10] != "B" else "C") + token[11:]
    import pytest
    with pytest.raises(ValueError):
        sec_module.decrypt_api_key(bad)


def test_legacy_ciphertext_still_decrypts():
    """An API-key that was encrypted before the salt strengthening must
    still decrypt after upgrading, otherwise users would silently lose
    their AI model configuration."""
    source = (settings.encryption_key or settings.secret_key or "change-me").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"cc-security-salt",
        iterations=100_000,
    )
    legacy_key = base64.urlsafe_b64encode(kdf.derive(source))
    legacy_fernet = Fernet(legacy_key)
    legacy_token = legacy_fernet.encrypt(b"legacy-key-value").decode()

    assert sec_module.decrypt_api_key(legacy_token) == "legacy-key-value"
