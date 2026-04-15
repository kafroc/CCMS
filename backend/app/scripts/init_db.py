"""
Database initialization script.
Run: python -m app.scripts.init_db
"""
import asyncio
import secrets
import string
import sys
import os

# Ensure app module is discoverable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.database import init_db, AsyncSessionLocal
from app.core.auth import hash_password
from app.core.config import settings
from app.models.user import User
from sqlmodel import select


_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_"


def _generate_password(length: int = 20) -> str:
    """Cryptographically-random password with mixed classes."""
    while True:
        pw = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(c.isupper() for c in pw)
            and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%^&*-_" for c in pw)
        ):
            return pw


async def seed_admin():
    """Create initial admin user if it doesn't exist.

    If ADMIN_INITIAL_PASSWORD is not set (recommended), a strong random
    password is generated and printed once. Either way, the admin account
    is flagged `must_change_password=True` so the first login forces a
    password change before anything else.
    """
    async with AsyncSessionLocal() as db:
        result = await db.exec(
            select(User).where(User.username == "admin", User.deleted_at.is_(None))
        )
        existing = result.first()
        if existing:
            # If admin exists but has never logged in (must_change_password still
            # set), re-sync the password to whatever ADMIN_INITIAL_PASSWORD says.
            # This covers re-runs after "docker compose down" (volume preserved)
            # where the password shown in print_credentials should still match.
            configured_password = (settings.admin_initial_password or "").strip()
            if existing.must_change_password and configured_password:
                existing.password_hash = hash_password(configured_password)
                db.add(existing)
                await db.commit()
                print("✓ Admin password re-synced to ADMIN_INITIAL_PASSWORD (first login not yet done).")
            else:
                print("✓ Admin user already exists — password untouched.")
            return

        configured_password = (settings.admin_initial_password or "").strip()
        if configured_password:
            password = configured_password
            origin = "from ADMIN_INITIAL_PASSWORD"
        else:
            password = _generate_password()
            origin = "auto-generated (store this somewhere safe — it will not be shown again)"

        admin = User(
            username="admin",
            password_hash=hash_password(password),
            role="admin",
            must_change_password=True,
        )
        db.add(admin)
        await db.commit()

        print("✓ Admin user created.")
        print("  NOTE: you will be required to change the password on first login.")


async def main():
    print("=== CC Security Management System - Database Initialization ===")
    print("1. Creating database tables...")
    await init_db()
    print("✓ Database tables created successfully")

    print("2. Initializing admin user...")
    await seed_admin()

    print("\n✅ Initialization complete!")
    print("   Login URL: http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(main())
