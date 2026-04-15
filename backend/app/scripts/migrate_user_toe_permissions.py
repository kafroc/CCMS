"""
Migration script: create the user_toe_permissions table.
Run: python -m app.scripts.migrate_user_toe_permissions
"""
import asyncio
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.database import engine


async def run_migration():
    print("=== user_toe_permissions Table Migration ===")
    async with engine.begin() as conn:
        await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_toe_permissions (
            user_id VARCHAR(36) NOT NULL,
            toe_id VARCHAR(36) NOT NULL,
            access_level VARCHAR(16) NOT NULL DEFAULT 'read',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL,
            deleted_at TIMESTAMP NULL,
            PRIMARY KEY (user_id, toe_id)
        )
        """))
        await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_user_toe_permissions_deleted_at
        ON user_toe_permissions (deleted_at)
        """))
    print("[OK] Migration complete.")


if __name__ == "__main__":
    asyncio.run(run_migration())