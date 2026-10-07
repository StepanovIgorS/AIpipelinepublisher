from typing import Any

import asyncpg

from api.config import settings


class Database:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    async def init_pool(self):
        self._pool = await asyncpg.create_pool(
            dsn=settings.POSTGRES_URL, min_size=5, max_size=10
        )

    async def fetchall(self, query: str, *args) -> list[asyncpg.Record] | None:
        if self._pool:
            async with self._pool.acquire() as connection:  # type: asyncpg.Connection
                return await connection.fetch(query, *args)
        return None

    async def fetchone(self, query: str, *args) -> asyncpg.Record | None:
        if self._pool:
            async with self._pool.acquire() as connection:  # type: asyncpg.Connection
                return await connection.fetchrow(query, *args)
        return None

    async def fetchval(self, query: str, *args) -> Any | None:
        if self._pool:
            async with self._pool.acquire() as connection:  # type: asyncpg.Connection
                return await connection.fetchval(query, *args)
        return None

    async def execute(self, query: str, *args) -> None:
        if self._pool:
            async with self._pool.acquire() as connection:  # type: asyncpg.Connection
                await connection.execute(query, *args)

    async def close(self):
        if self._pool:
            await self._pool.close()
