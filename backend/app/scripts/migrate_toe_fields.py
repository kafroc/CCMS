"""
Database migration script: add or update fields for the TOE module.
Run: python -m app.scripts.migrate_toe_fields

New fields (toes table):
  Round 1: usage_and_security_features, required_non_toe_hw_sw_fw, hw_interfaces, sw_interfaces
  Round 2: toe_type_desc, toe_usage, major_security_features, physical_scope, logical_scope
New fields (toe_files table):
  Round 1: file_category
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from app.core.database import engine


ALTER_STATEMENTS = [
    # ── toes table Round 1 ──
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS usage_and_security_features TEXT",
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS required_non_toe_hw_sw_fw TEXT",
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS hw_interfaces TEXT",
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS sw_interfaces TEXT",
    # ── toes table Round 2 ──
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS toe_type_desc TEXT",
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS toe_usage TEXT",
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS major_security_features TEXT",
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS physical_scope TEXT",
    "ALTER TABLE toes ADD COLUMN IF NOT EXISTS logical_scope TEXT",
    # ── toe_files table ──
    "ALTER TABLE toe_files ADD COLUMN IF NOT EXISTS file_category VARCHAR(32) NOT NULL DEFAULT 'manual'",
]


async def run_migration():
    print("=== TOE Field Migration ===")
    async with engine.begin() as conn:
        for stmt in ALTER_STATEMENTS:
            print(f"Executing: {stmt}")
            await conn.execute(text(stmt))
    print("\n[OK] Migration complete.")


if __name__ == "__main__":
    asyncio.run(run_migration())
