import asyncpg

from app.core.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def open_pool():
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL)


async def close_pool():
    await _pool.close()


def db() -> asyncpg.Pool:
    return _pool
