"""
Migration: Add timeout_seconds and is_active fields to ai_models table
Run: cd backend && python -m scripts.migrate_ai_model_v2
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine


async def migrate():
    async with engine.begin() as conn:
        # Check if column exists before adding, to avoid re-execution errors
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='ai_models' AND column_name='timeout_seconds'"
        ))
        if not result.fetchone():
            await conn.execute(text(
                "ALTER TABLE ai_models ADD COLUMN timeout_seconds INTEGER NOT NULL DEFAULT 60"
            ))
            print("✓ Added timeout_seconds column")
        else:
            print("- timeout_seconds column already exists, skipping")

        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='ai_models' AND column_name='is_active'"
        ))
        if not result.fetchone():
            await conn.execute(text(
                "ALTER TABLE ai_models ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            print("✓ Added is_active column")
        else:
            print("- is_active column already exists, skipping")

    print("Migration complete")


if __name__ == "__main__":
    asyncio.run(migrate())
