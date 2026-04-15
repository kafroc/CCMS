"""
Database migration script: add editable fields to the sfrs table.
Run: python -m app.scripts.migrate_sfr_fields
"""
import asyncio
import os
import selectors
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from app.core.database import AsyncSessionLocal


async def run_migration():
    print("=== SFR Fields Migration ===")
    alter_statements = [
        "ALTER TABLE sfrs ADD COLUMN IF NOT EXISTS sfr_name VARCHAR(256)",
        "ALTER TABLE sfrs ADD COLUMN IF NOT EXISTS sfr_detail TEXT",
        "ALTER TABLE sfrs ADD COLUMN IF NOT EXISTS dependency TEXT",
    ]

    async with AsyncSessionLocal() as db:
        try:
            for stmt in alter_statements:
                print(f"Executing: {stmt}")
                await db.execute(text(stmt))
                await db.commit()
            print("[OK] Migration complete.")
        except Exception as exc:
            print(f"Error: {exc}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(run_migration(), loop_factory=asyncio.SelectorEventLoop)