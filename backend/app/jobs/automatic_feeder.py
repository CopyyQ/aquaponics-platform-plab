from __future__ import annotations

from datetime import datetime

from app.db.session import async_session_factory
from app.services.automatic_feeder_runtime_service import scan_automatic_feeder_schedules


async def run_automatic_feeder_scheduler(*, now: datetime | None = None) -> int:
    async with async_session_factory() as db:
        created = await scan_automatic_feeder_schedules(db, now=now)
        await db.commit()
        return created
