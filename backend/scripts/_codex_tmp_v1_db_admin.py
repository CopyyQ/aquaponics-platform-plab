from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
from sqlalchemy.engine import make_url


async def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"recreate", "drop"}:
        raise SystemExit("usage: _codex_tmp_v1_db_admin.py recreate|drop DB")
    action, name = sys.argv[1:]
    if not name.startswith(("aquaponics_codex_", "aquaponics_test_", "aquaponics_fresh_")):
        raise RuntimeError(f"Refusing non-disposable database name: {name}")
    url = make_url(os.environ["DATABASE_URL"])
    connection = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{name}"')
        if action == "recreate":
            await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()
    print(f"{action.upper()}={name}")


if __name__ == "__main__":
    asyncio.run(main())
