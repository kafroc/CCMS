"""
Migration: Create blind_spot_suggestions table.
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine


async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS blind_spot_suggestions (
                id VARCHAR PRIMARY KEY,
                toe_id VARCHAR NOT NULL REFERENCES toes(id),
                category VARCHAR(32) NOT NULL,
                content TEXT NOT NULL,
                is_ignored BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP,
                deleted_at TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_blind_spot_suggestions_toe_id
            ON blind_spot_suggestions(toe_id)
        """))
    print("Migration complete: blind_spot_suggestions table created.")


if __name__ == "__main__":
    asyncio.run(migrate())
