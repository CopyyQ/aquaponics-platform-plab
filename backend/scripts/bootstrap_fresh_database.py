"""Bootstrap an explicitly disposable database through Alembic and canonical seed.

Migrations own the schema and ``scripts.seed`` owns the current installation
catalog.  No legacy Energy Monitor provisioning runs here.
"""

import asyncio
import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import engine
from scripts.seed import seed

ALLOWED_DATABASE_PREFIXES = ("aquaponics_codex_", "aquaponics_test_", "aquaponics_fresh_")


async def _assert_empty_disposable_database() -> None:
    try:
        async with engine.connect() as connection:
            database_name = await connection.scalar(text("SELECT current_database()"))
            if not isinstance(database_name, str) or not database_name.startswith(ALLOWED_DATABASE_PREFIXES):
                raise RuntimeError(f"Refusing bootstrap outside a disposable database: {database_name!r}")
            tables = await connection.run_sync(lambda sync_connection: inspect(sync_connection).get_table_names())
            if tables:
                raise RuntimeError("Refusing bootstrap because the database is not empty: " + ", ".join(sorted(tables)))
    finally:
        await engine.dispose()


async def _seed_and_dispose() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


def bootstrap() -> None:
    asyncio.run(_assert_empty_disposable_database())
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    asyncio.run(_seed_and_dispose())
    print("Fresh canonical bootstrap completed at Alembic head")


if __name__ == "__main__":
    bootstrap()
