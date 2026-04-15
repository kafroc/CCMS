from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional, List


# A list of well-known weak / placeholder secret values that must never be
# accepted in a production environment.
_WEAK_SECRETS = {
    "",
    "change-me",
    "changeme",
    "change-me-to-a-random-32-byte-string",
    "secret",
    "please-change",
    "dev",
    "development",
}

_WEAK_ADMIN_PASSWORDS = {
    "admin",
    "admin123",
    "password",
    "123456",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "CC Security Management System"
    app_env: str = "development"
    debug: bool = True

    # Security
    secret_key: str = "change-me"
    access_token_expire_hours: int = 8
    algorithm: str = "HS256"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/cc_security"
    sync_database_url: str = "postgresql+psycopg2://postgres:password@localhost:5432/cc_security"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # File storage
    storage_path: str = "./storage"
    max_upload_size_mb: int = 500

    # Initial admin. When empty, a random password is generated during
    # `python -m app.scripts.init_db` and printed once to stdout. The admin
    # account is always seeded with must_change_password=True.
    admin_initial_password: Optional[str] = None

    # Encryption key for AI API-key encrypted storage. Required in production.
    encryption_key: Optional[str] = None

    # CORS: comma-separated list of allowed origins. If left empty in
    # development a sensible local default is used. In production, this
    # MUST be explicitly set.
    allowed_origins: str = ""

    # PDF parsing timeout (seconds), can be overridden by database system settings
    pdf_parse_timeout_seconds: int = 300

    @property
    def upload_max_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @property
    def cors_origins(self) -> List[str]:
        raw = (self.allowed_origins or "").strip()
        if not raw:
            if self.is_production:
                return []  # no defaults in production — must be configured
            return [
                "http://localhost:5173",
                "http://localhost:3000",
                "http://localhost:80",
                "http://localhost",
            ]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def validate_for_runtime(self) -> List[str]:
        """Return a list of configuration errors. Empty list = OK.

        Production has strict requirements; development is permissive but
        emits warnings (still returned as strings so the caller can log them).
        """
        errors: List[str] = []
        warnings: List[str] = []

        # ── secret_key ────────────────────────────────────────────────
        sk = (self.secret_key or "").strip()
        if sk.lower() in _WEAK_SECRETS:
            msg = (
                "SECRET_KEY is set to a weak/default value. "
                "Generate a strong one, e.g. `python -c \"import secrets; print(secrets.token_urlsafe(64))\"`"
            )
            (errors if self.is_production else warnings).append(msg)
        elif len(sk) < 32:
            msg = f"SECRET_KEY must be at least 32 chars (current: {len(sk)})."
            (errors if self.is_production else warnings).append(msg)

        # ── encryption_key (for AI API keys at rest) ─────────────────
        if self.is_production and not (self.encryption_key or "").strip():
            errors.append(
                "ENCRYPTION_KEY must be set in production. "
                "Generate with: `python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`"
            )

        # ── CORS origins ─────────────────────────────────────────────
        if self.is_production and not self.cors_origins:
            errors.append(
                "ALLOWED_ORIGINS must be set in production (comma-separated list)."
            )

        # ── initial admin password ───────────────────────────────────
        pw = (self.admin_initial_password or "").strip()
        if pw and pw in _WEAK_ADMIN_PASSWORDS:
            (errors if self.is_production else warnings).append(
                "ADMIN_INITIAL_PASSWORD is set to a well-known weak value. "
                "Leave it unset to auto-generate a random password on init_db."
            )

        # Store warnings where caller can pick them up.
        self._warnings = warnings  # type: ignore[attr-defined]
        return errors

    @property
    def warnings(self) -> List[str]:
        return getattr(self, "_warnings", [])


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
