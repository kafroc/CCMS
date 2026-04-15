"""Tests for the production safeguards in app.core.config.Settings."""
from app.core.config import Settings


def _make(**overrides):
    base = dict(
        app_env="production",
        secret_key="please-change-this-in-prod-" + "x" * 40,
        encryption_key="A" * 43 + "=",  # 32-byte b64 -> 44 chars; not real Fernet but passes len check
        allowed_origins="https://app.example.com",
        admin_initial_password=None,
    )
    base.update(overrides)
    return Settings(**base)


def test_strong_production_config_ok():
    errs = _make().validate_for_runtime()
    assert errs == []


def test_weak_secret_key_rejected_in_prod():
    errs = _make(secret_key="change-me").validate_for_runtime()
    assert any("SECRET_KEY" in e for e in errs)


def test_short_secret_key_rejected_in_prod():
    errs = _make(secret_key="short").validate_for_runtime()
    assert any("SECRET_KEY" in e for e in errs)


def test_missing_encryption_key_rejected_in_prod():
    errs = _make(encryption_key=None).validate_for_runtime()
    assert any("ENCRYPTION_KEY" in e for e in errs)


def test_missing_cors_rejected_in_prod():
    errs = _make(allowed_origins="").validate_for_runtime()
    assert any("ALLOWED_ORIGINS" in e for e in errs)


def test_weak_admin_password_rejected_in_prod():
    errs = _make(admin_initial_password="Admin@123456").validate_for_runtime()
    assert any("ADMIN_INITIAL_PASSWORD" in e for e in errs)


def test_development_only_warns():
    s = Settings(
        app_env="development",
        secret_key="change-me",
        encryption_key=None,
        allowed_origins="",
    )
    # dev: no hard errors, only warnings
    assert s.validate_for_runtime() == []
    assert any("SECRET_KEY" in w for w in s.warnings)


def test_cors_origins_parse():
    s = Settings(
        app_env="development",
        allowed_origins="https://a.test, https://b.test",
        secret_key="dev-secret-key-must-be-long-" + "x" * 20,
    )
    assert s.cors_origins == ["https://a.test", "https://b.test"]
