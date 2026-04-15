"""Migration: add `users.must_change_password` column + create `audit_logs`
and `error_logs` tables.

Run once after upgrading:
    python -m app.scripts.migrate_add_logs_and_user_flag

Idempotent: safe to re-run. Compatible with PostgreSQL and SQLite.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from app.core.database import engine


def _is_postgres(dialect_name: str) -> bool:
    return dialect_name.startswith("postgres")


async def run_migration():
    print("=== Add audit_logs / error_logs tables + users.must_change_password ===")
    async with engine.begin() as conn:
        dialect = conn.dialect.name
        print(f"Dialect: {dialect}")

        # 1. Add must_change_password column to users if missing.
        if _is_postgres(dialect):
            # Check if users table exists at all (new install: init_db will create it with the column).
            table_exists = (await conn.execute(text("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'users' AND table_schema = 'public'
            """))).first()
            if not table_exists:
                print("[skip] users table does not exist yet — init_db will create it")
            else:
                # Check column existence via information_schema.
                q = text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'must_change_password'
                """)
                exists = (await conn.execute(q)).first()
                if exists:
                    print("[skip] users.must_change_password already present")
                else:
                    print("[run]  ALTER TABLE users ADD COLUMN must_change_password BOOLEAN ...")
                    await conn.execute(text(
                        "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE"
                    ))
        else:
            # SQLite: try pragma; on failure just attempt the ALTER (it's idempotent enough for dev).
            try:
                rows = list((await conn.execute(text("PRAGMA table_info(users)"))).all())
                names = {r[1] for r in rows}
                if "must_change_password" in names:
                    print("[skip] users.must_change_password already present")
                else:
                    await conn.execute(text(
                        "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"
                    ))
                    print("[ok]   users.must_change_password added")
            except Exception as e:
                print(f"[warn] could not introspect users table: {e}")

        # 2. Create audit_logs.
        print("[run]  CREATE TABLE IF NOT EXISTS audit_logs ...")
        if _is_postgres(dialect):
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id VARCHAR PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL,
                    user_id VARCHAR(64),
                    username VARCHAR(64),
                    method VARCHAR(8) NOT NULL,
                    path VARCHAR(512) NOT NULL,
                    status_code INTEGER NOT NULL DEFAULT 0,
                    resource VARCHAR(64),
                    resource_id VARCHAR(64),
                    ip VARCHAR(64),
                    user_agent VARCHAR(256),
                    duration_ms INTEGER,
                    extra TEXT
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_resource ON audit_logs (resource)"
            ))
        else:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id VARCHAR PRIMARY KEY,
                    created_at DATETIME NOT NULL,
                    user_id VARCHAR(64),
                    username VARCHAR(64),
                    method VARCHAR(8) NOT NULL,
                    path VARCHAR(512) NOT NULL,
                    status_code INTEGER NOT NULL DEFAULT 0,
                    resource VARCHAR(64),
                    resource_id VARCHAR(64),
                    ip VARCHAR(64),
                    user_agent VARCHAR(256),
                    duration_ms INTEGER,
                    extra TEXT
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_resource ON audit_logs (resource)"
            ))

        # 3. Create error_logs.
        print("[run]  CREATE TABLE IF NOT EXISTS error_logs ...")
        if _is_postgres(dialect):
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id VARCHAR PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL,
                    level VARCHAR(16) NOT NULL DEFAULT 'ERROR',
                    error_type VARCHAR(128) NOT NULL DEFAULT 'Exception',
                    message TEXT NOT NULL,
                    stack_trace TEXT,
                    user_id VARCHAR(64),
                    username VARCHAR(64),
                    method VARCHAR(8),
                    path VARCHAR(512),
                    ip VARCHAR(64)
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_error_logs_created_at ON error_logs (created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_error_logs_user_id ON error_logs (user_id)"
            ))
        else:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id VARCHAR PRIMARY KEY,
                    created_at DATETIME NOT NULL,
                    level VARCHAR(16) NOT NULL DEFAULT 'ERROR',
                    error_type VARCHAR(128) NOT NULL DEFAULT 'Exception',
                    message TEXT NOT NULL,
                    stack_trace TEXT,
                    user_id VARCHAR(64),
                    username VARCHAR(64),
                    method VARCHAR(8),
                    path VARCHAR(512),
                    ip VARCHAR(64)
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_error_logs_created_at ON error_logs (created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_error_logs_user_id ON error_logs (user_id)"
            ))

    print("[OK] Migration complete.")


if __name__ == "__main__":
    asyncio.run(run_migration())
