"""
Database migration script: add new fields to the test_cases table.
Run: python -m app.scripts.migrate_test_case_fields

New fields (test_cases table):
    - test_target: test target
    - test_scenario: test scenario
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from app.core.database import engine


ALTER_STATEMENTS = [
    "ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS test_target TEXT",
    "ALTER TABLE test_cases ADD COLUMN IF NOT EXISTS test_scenario TEXT",
]


async def run_migration():
    print("=== TestCase Field Migration ===")
    async with engine.begin() as conn:
        for stmt in ALTER_STATEMENTS:
            print(f"Executing: {stmt}")
            await conn.execute(text(stmt))
    print("\n[OK] Migration complete.")


if __name__ == "__main__":
    asyncio.run(run_migration())
