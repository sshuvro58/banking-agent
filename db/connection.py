"""
Database Connection — asyncpg connection pool.

Usage:
    await db.connect()
    result = await db.fetchrow("SELECT * FROM banking.customers WHERE customer_id = $1", "cust_001")
    await db.disconnect()
"""
import asyncpg
import logging
from config import db_config

logger = logging.getLogger("database")


class Database:
    """Manages an asyncpg connection pool for the whole app."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        """Create the connection pool. Call once at startup."""
        self.pool = await asyncpg.create_pool(
            host=db_config.host,
            port=db_config.port,
            database=db_config.name,
            user=db_config.user,
            password=db_config.password,
            min_size=2,
            max_size=10,
        )
        logger.info(f"[DB] Pool created: {db_config.host}:{db_config.port}/{db_config.name}")

    async def disconnect(self):
        """Close the pool. Call on shutdown."""
        if self.pool:
            await self.pool.close()
            logger.info("[DB] Pool closed")

    async def execute(self, query: str, *args) -> str:
        """Run a query that doesn't return rows (INSERT, UPDATE, DELETE)."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Run a query and return all rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """Run a query and return one row (or None)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Run a query and return a single value."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)


# Singleton
db = Database()