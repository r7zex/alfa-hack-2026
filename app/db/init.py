"""Explicit one-time schema initialization for the MVP.

Run: python -m app.db.init
Replace create_all with versioned Alembic migrations before schema evolution.
"""
import asyncio

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
import app.models.loan_application  # noqa: F401 - register metadata


async def main() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # Local-development compatibility: create_all does not alter tables
        # created before current_step existed. Alembic owns later migrations.
        await connection.execute(text(
            "ALTER TABLE loan_applications "
            "ADD COLUMN IF NOT EXISTS current_step INTEGER NOT NULL DEFAULT 0"
        ))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
