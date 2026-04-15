"""
Migration script: create the system_settings table.
Run: python -m app.scripts.migrate_system_settings
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from app.core.database import engine


async def run_migration():
    print("=== system_settings Table Migration ===")
    async with engine.begin() as conn:
        stmt = """
        CREATE TABLE IF NOT EXISTS system_settings (
            key VARCHAR(64) PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
        print("Executing: CREATE TABLE IF NOT EXISTS system_settings ...")
        await conn.execute(text(stmt))
    print("[OK] Migration complete.")


if __name__ == "__main__":
    asyncio.run(run_migration())
