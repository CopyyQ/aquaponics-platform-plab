from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.models.actuator import Actuator
from app.models.automatic_feeder import (
    AutomaticFeederConfig,
    AutomaticFeederEvent,
    AutomaticFeederScheduleSlot,
    FeederEventStatus,
    FeedLevel,
)
from app.schemas.actuator import AutomaticFeederCommandParams
from app.schemas.automatic_feeder import AutomaticFeederUpdate

AUTOMATIC_FEEDER_MODEL_CODE = "AUTOMATIC_FEEDER"
DEFAULT_FEEDER_SCHEDULE = (time(0, 0), time(8, 0), time(16, 0))


async def ensure_automatic_feeder_config(
    db: AsyncSession,
    *,
    actuator: Actuator,
) -> AutomaticFeederConfig:
    """Create feeder defaults once while preserving every later user edit."""
    config = await db.scalar(
        select(AutomaticFeederConfig)
        .options(selectinload(AutomaticFeederConfig.slots))
        .where(AutomaticFeederConfig.actuator_id == actuator.id)
    )
    if config is None:
        config = AutomaticFeederConfig(
            actuator_id=actuator.id,
            feed_level=FeedLevel.LEVEL_1.value,
            schedule_enabled=True,
        )
        db.add(config)
        await db.flush()
        existing_slots: list[AutomaticFeederScheduleSlot] = []
    else:
        existing_slots = list(config.slots)

    existing_by_number = {slot.slot_number: slot for slot in existing_slots}
    used_times = {slot.feed_time for slot in existing_slots}
    available_defaults = [item for item in DEFAULT_FEEDER_SCHEDULE if item not in used_times]
    for slot_number in range(1, 4):
        if slot_number in existing_by_number:
            continue
        if not available_defaults:
            raise RuntimeError("AUTOMATIC_FEEDER_DEFAULT_SCHEDULE_EXHAUSTED")
        slot = AutomaticFeederScheduleSlot(
            feeder_config_id=config.id,
            slot_number=slot_number,
            feed_time=available_defaults.pop(0),
        )
        db.add(slot)
        existing_slots.append(slot)
    await db.flush()
    return config


def is_automatic_feeder(actuator: Actuator) -> bool:
    return bool(
        actuator.actuator_model is not None
        and actuator.actuator_model.code == AUTOMATIC_FEEDER_MODEL_CODE
    )


def _next_feed_at(
    config: AutomaticFeederConfig,
    *,
    now: datetime,
) -> datetime | None:
    if not config.schedule_enabled or not config.slots:
        return None
    timezone = ZoneInfo(settings.display_timezone)
    local_now = now.astimezone(timezone)
    feed_times = sorted(slot.feed_time for slot in config.slots)
    for feed_time in feed_times:
        candidate = datetime.combine(local_now.date(), feed_time, tzinfo=timezone)
        if candidate > local_now:
            return candidate.astimezone(UTC)
    rollover = datetime.combine(
        local_now.date() + timedelta(days=1),
        feed_times[0],
        tzinfo=timezone,
    )
    return rollover.astimezone(UTC)


async def _feeder_runtime_projection(
    db: AsyncSession,
    *,
    actuator_id: int,
) -> tuple[dict | None, datetime | None]:
    running = await db.scalar(
        select(AutomaticFeederEvent)
        .where(
            AutomaticFeederEvent.actuator_id == actuator_id,
            AutomaticFeederEvent.status == FeederEventStatus.RUNNING.value,
        )
        .order_by(
            AutomaticFeederEvent.started_at.desc().nullslast(),
            AutomaticFeederEvent.id.desc(),
        )
        .limit(1)
    )
    completed = await db.scalar(
        select(AutomaticFeederEvent)
        .where(
            AutomaticFeederEvent.actuator_id == actuator_id,
            AutomaticFeederEvent.status == FeederEventStatus.COMPLETED.value,
            AutomaticFeederEvent.ended_at.is_not(None),
        )
        .order_by(AutomaticFeederEvent.ended_at.desc(), AutomaticFeederEvent.id.desc())
        .limit(1)
    )
    current_feed = None
    if running is not None:
        current_feed = {
            "event_id": running.id,
            "source": running.source,
            "status": running.status,
            "feed_level": running.feed_level,
            "free_output_value": running.free_output_value,
            "free_output_unit": running.free_output_unit,
            "scheduled_at": running.scheduled_at,
            "started_at": running.started_at,
        }
    return current_feed, completed.ended_at if completed is not None else None


async def get_automatic_feeder_read(
    db: AsyncSession,
    *,
    actuator: Actuator,
    now: datetime | None = None,
) -> dict | None:
    if not is_automatic_feeder(actuator):
        return None
    config = await db.scalar(
        select(AutomaticFeederConfig)
        .options(selectinload(AutomaticFeederConfig.slots))
        .execution_options(populate_existing=True)
        .where(AutomaticFeederConfig.actuator_id == actuator.id)
    )
    if config is None:
        config = await ensure_automatic_feeder_config(db, actuator=actuator)
        config = await db.scalar(
            select(AutomaticFeederConfig)
            .options(selectinload(AutomaticFeederConfig.slots))
            .execution_options(populate_existing=True)
            .where(AutomaticFeederConfig.id == config.id)
        )
    assert config is not None
    current_feed, last_feed_at = await _feeder_runtime_projection(
        db, actuator_id=actuator.id
    )
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    return {
        "feed_level": config.feed_level,
        "free_output_value": config.free_output_value,
        "free_output_unit": config.free_output_unit,
        "schedule_enabled": config.schedule_enabled,
        "schedule": [
            slot.feed_time.strftime("%H:%M")
            for slot in sorted(config.slots, key=lambda item: item.slot_number)
        ],
        "current_feed": current_feed,
        "last_feed_at": last_feed_at,
        "next_feed_at": _next_feed_at(config, now=timestamp),
    }


async def update_automatic_feeder_config(
    db: AsyncSession,
    *,
    actuator: Actuator,
    payload: AutomaticFeederUpdate,
) -> dict:
    if not is_automatic_feeder(actuator):
        raise ApplicationError(
            "AUTOMATIC_FEEDER_REQUIRED",
            "Actuator này không phải máy cho ăn tự động.",
            422,
        )
    config = await ensure_automatic_feeder_config(db, actuator=actuator)
    changes = payload.model_dump(exclude_unset=True)
    schedule = changes.pop("schedule", None)
    if isinstance(changes.get("feed_level"), FeedLevel):
        changes["feed_level"] = changes["feed_level"].value

    next_level = str(changes.get("feed_level", config.feed_level))
    next_free_value = changes.get("free_output_value", config.free_output_value)
    next_free_unit = changes.get("free_output_unit", config.free_output_unit)
    if next_level == FeedLevel.FREE.value:
        if next_free_value is None or not next_free_unit:
            raise ApplicationError(
                "AUTOMATIC_FEEDER_FREE_OUTPUT_REQUIRED",
                "Mức FREE yêu cầu free_output_value và free_output_unit.",
                422,
            )
    else:
        if (
            changes.get("free_output_value") is not None
            or changes.get("free_output_unit") is not None
        ):
            raise ApplicationError(
                "AUTOMATIC_FEEDER_FREE_OUTPUT_INVALID",
                "Chỉ mức FREE được phép cấu hình đầu ra tự do.",
                422,
            )
        config.free_output_value = None
        config.free_output_unit = None

    for field, value in changes.items():
        setattr(config, field, value)
    if schedule is not None:
        parsed = [time.fromisoformat(value) for value in schedule]
        await db.execute(
            delete(AutomaticFeederScheduleSlot).where(
                AutomaticFeederScheduleSlot.feeder_config_id == config.id
            )
        )
        await db.flush()
        for slot_number, feed_time in enumerate(parsed, start=1):
            db.add(
                AutomaticFeederScheduleSlot(
                    feeder_config_id=config.id,
                    slot_number=slot_number,
                    feed_time=feed_time,
                )
            )
    await db.flush()
    result = await get_automatic_feeder_read(db, actuator=actuator)
    assert result is not None
    return result

async def build_feed_command_payload(
    db: AsyncSession,
    *,
    actuator: Actuator,
    params: AutomaticFeederCommandParams | None,
) -> dict:
    if not is_automatic_feeder(actuator):
        raise ApplicationError(
            "AUTOMATIC_FEEDER_REQUIRED",
            "Actuator này không phải máy cho ăn tự động.",
            422,
        )
    current = await get_automatic_feeder_read(db, actuator=actuator)
    assert current is not None
    overrides = params.model_dump(exclude_unset=True) if params is not None else {}
    level = overrides.get("feed_level", current["feed_level"])
    if isinstance(level, FeedLevel):
        level = level.value
    free_value = overrides.get("free_output_value", current["free_output_value"])
    free_unit = overrides.get("free_output_unit", current["free_output_unit"])
    if level == FeedLevel.FREE.value:
        if free_value is None or not free_unit:
            raise ApplicationError(
                "AUTOMATIC_FEEDER_FREE_OUTPUT_REQUIRED",
                "Mức FREE yêu cầu free_output_value và free_output_unit.",
                422,
            )
    else:
        if (
            overrides.get("free_output_value") is not None
            or overrides.get("free_output_unit") is not None
        ):
            raise ApplicationError(
                "AUTOMATIC_FEEDER_FREE_OUTPUT_INVALID",
                "Chỉ mức FREE được phép cấu hình đầu ra tự do.",
                422,
            )
        free_value = None
        free_unit = None
    return {
        "feed_level": level,
        "free_output_value": free_value,
        "free_output_unit": free_unit,
    }
