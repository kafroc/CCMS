"""
ARQ connection pool singleton for importing across route modules.
Initialized and closed during the FastAPI lifespan.
"""
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from app.core.config import settings

arq_pool: ArqRedis = None  # type: ignore


async def init_arq_pool():
    global arq_pool
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def close_arq_pool():
    global arq_pool
    if arq_pool:
        await arq_pool.close()
        arq_pool = None
