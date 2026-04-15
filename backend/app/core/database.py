from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import AsyncGenerator
from app.core.config import settings


def _resolve_async_database_url() -> str:
    url = settings.database_url
    if not url.startswith("postgresql+asyncpg://"):
        return url
    try:
        __import__("asyncpg")
        return url
    except ModuleNotFoundError:
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

_db_url = _resolve_async_database_url()
_engine_kwargs = {"echo": settings.debug, "pool_pre_ping": True}
# SQLite (used by tests) doesn't support pool_size/max_overflow. For
# in-memory SQLite we must use StaticPool so every session shares the
# same in-memory database; file-based SQLite can use the default pool.
if _db_url.startswith("sqlite"):
    # For in-memory SQLite we must use StaticPool (single shared
    # connection) so every session sees the same DB. For file-based
    # SQLite (dev/tests) the default pool works and gives real
    # concurrency with WAL mode.
    if ":memory:" in _db_url:
        from sqlalchemy.pool import StaticPool
        _engine_kwargs["poolclass"] = StaticPool
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(_db_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all database tables."""
    import app.models  # noqa: F401 — ensure all models are registered
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db():
    """Close the database connection pool."""
    await engine.dispose()
