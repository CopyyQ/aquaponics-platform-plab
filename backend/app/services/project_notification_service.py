"""Project operational transitions stay in the application, not Telegram.

Telegram delivery is intentionally limited to canonical OperationalIncident
OPEN/RECOVERED events. Device connectivity, actuator command transitions,
project health summaries and legacy alert transitions must not create Telegram
outbox rows.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


def format_display_time(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        return "—"
    try:
        zone = ZoneInfo(settings.display_timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return f"{value.astimezone(zone).strftime('%d/%m/%Y %H:%M:%S')} ({settings.display_timezone})"


async def dispatch_device_connectivity_transition(
    db: AsyncSession,
    *,
    device_id: int,
    transition: str,
    occurred_at: datetime | None = None,
    **_: object,
) -> None:
    del db, device_id, transition, occurred_at
    return None


async def dispatch_actuator_command_transition(
    db: AsyncSession,
    *,
    command_id: int,
    transition: str,
    **_: object,
) -> None:
    del db, command_id, transition
    return None


async def dispatch_project_health_message(
    db: AsyncSession,
    *,
    project_id: int,
    message: str,
    **_: object,
) -> None:
    del db, project_id, message
    return None


async def dispatch_alert_transition(*_: object, **__: object) -> None:
    """Retired legacy SensorAlert dispatcher; canonical alerts use incidents."""
    return None
