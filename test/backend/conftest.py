"""Shared pytest fixtures for the backend test suite.

Design decisions:

* **In-memory SQLite** — tests are fully hermetic. They don't need a
  running PostgreSQL. SQLModel is DB-agnostic enough for this project.
* **Per-test database** — each test gets a fresh schema via the
  ``clean_db`` fixture and rolls back any state.
* **ARQ stubbed** — ``init_arq_pool`` / ``close_arq_pool`` are replaced
  with no-ops so tests don't require Redis.
* **Audit middleware disabled** during DB-heavy tests to keep output
  clean. It has its own dedicated test file.
"""
from __future__ import annotations

import os
import sys
import asyncio
from pathlib import Path
from typing import AsyncIterator

# Ensure backend module is importable regardless of pytest invocation dir.
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

# Force a test-friendly configuration BEFORE importing the app.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-length-32-chars-" + "x" * 20)
# Use a file-based SQLite (not :memory:) so every session sees the
# same database. With aiosqlite, each underlying connection is opened in
# its own worker thread; two threads sharing ":memory:" get disjoint DBs.
_TEST_DB_PATH = _REPO / "test" / ".tmp_test.db"
_TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if _TEST_DB_PATH.exists():
    _TEST_DB_PATH.unlink()
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}")
os.environ.setdefault("SYNC_DATABASE_URL", f"sqlite:///{_TEST_DB_PATH.as_posix()}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "TestAdminPw!2345")
os.environ.setdefault("STORAGE_PATH", str(_REPO / "test" / ".tmp_storage"))
os.environ.setdefault("ALLOWED_ORIGINS", "http://testserver")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Import *after* env vars are in place so pydantic-settings sees them.
from app.core import config as config_module  # noqa: E402
config_module.get_settings.cache_clear()
config_module.settings = config_module.get_settings()

from app.core.database import AsyncSessionLocal, engine  # noqa: E402

# Enable SQLite WAL journal mode on each raw connection so the audit-log
# middleware (which writes from a separate session during the main
# request transaction) doesn't hit "database is locked". File-based
# SQLite without WAL serializes readers/writers hard.
from sqlalchemy import event as _sa_event  # noqa: E402
@_sa_event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_wal(dbapi_conn, _):  # noqa: ANN001
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
    except Exception:
        pass
from app.core.auth import hash_password  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
import app.models  # noqa: F401,E402 — register all tables
from app.models.user import User  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Recreate the schema before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """FastAPI TestClient using httpx+ASGI, with ARQ pool stubbed."""
    import app.worker.worker as worker_mod
    from unittest.mock import AsyncMock

    worker_mod.init_arq_pool = AsyncMock(return_value=None)
    worker_mod.close_arq_pool = AsyncMock(return_value=None)

    from app.main import app
    # raise_app_exceptions=False: we WANT the global exception handler to
    # turn RuntimeError into a 500 response (and persist an ErrorLog row)
    # instead of httpx re-raising it as a client-side error.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user() -> User:
    """Insert a known admin user."""
    async with AsyncSessionLocal() as db:
        user = User(
            username="admin",
            password_hash=hash_password("AdminPw!2345"),
            role="admin",
            must_change_password=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest_asyncio.fixture
async def normal_user() -> User:
    async with AsyncSessionLocal() as db:
        user = User(
            username="alice",
            password_hash=hash_password("AlicePw!2345"),
            role="user",
            must_change_password=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient, admin_user: User) -> str:
    res = await client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "AdminPw!2345"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def user_token(client: AsyncClient, normal_user: User) -> str:
    res = await client.post(
        "/api/auth/login",
        data={"username": "alice", "password": "AlicePw!2345"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
