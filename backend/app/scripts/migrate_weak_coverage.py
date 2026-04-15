"""
Database migration script: add the weak_coverage_ignored field to the toe_assets table.
Run: python -m app.scripts.migrate_weak_coverage
"""
import asyncio
import sys
import os
import selectors

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from app.core.database import AsyncSessionLocal


async def run_migration():
    print("=== TOE Assets Weak Coverage Migration ===")
    
    ALTER_STATEMENTS = [
        "ALTER TABLE toe_assets ADD COLUMN IF NOT EXISTS weak_coverage_ignored BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    
    async with AsyncSessionLocal() as db:
        try:
            for stmt in ALTER_STATEMENTS:
                print(f"Executing: {stmt}")
                await db.execute(text(stmt))
                await db.commit()
            print("\n[OK] Migration complete.")
        except Exception as e:
            print(f"Error: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(run_migration(), loop_factory=asyncio.SelectorEventLoop)
