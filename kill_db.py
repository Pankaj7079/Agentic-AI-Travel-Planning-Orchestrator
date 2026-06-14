import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from parikrama.config import settings


async def kill_connections():
    engine = create_async_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(
            text("""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = current_database()
              AND pid <> pg_backend_pid();
        """)
        )
    print("Connections killed")


asyncio.run(kill_connections())
