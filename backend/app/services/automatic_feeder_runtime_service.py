from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.actuator import Actuator, ActuatorCommand
from app.models.automatic_feeder import (
    AutomaticFeederConfig,
    AutomaticFeederEvent,
    FeederEventSource,
    FeederEventStatus,
)
from app.models.device import Device
from app.models.project import Project
from app.services.actuator_command_service import create_actuator_command
from app.services.notification_outbox_service import enqueue_operational_event


def _scheduled_utc(local_date, feed_time) -> datetime:
    tz = ZoneInfo(settings.display_timezone)
    local_dt = datetime.combine(local_date, feed_time, tzinfo=tz)
    return local_dt.astimezone(UTC)


def _config_created_at_utc(config: AutomaticFeederConfig) -> datetime:
    created = config.created_at
    if created.tzinfo is None:
        return created.replace(tzinfo=UTC)
    return created.astimezone(UTC)


async def _enqueue_feeder_outcome(
    db: AsyncSession,
    *,
    event: AutomaticFeederEvent,
    event_type: str,
) -> None:
    row = (
        await db.execute(
            select(Actuator, Device, Project)
            .join(Device, Device.id == Actuator.device_id)
            .join(Project, Project.id == Device.project_id)
            .where(Actuator.id == event.actuator_id)
        )
    ).first()
    if row is None:
        return
    actuator, device, project = row
    await enqueue_operational_event(
        db,
        project_id=project.id,
        source_key=f"feeder-event:{event.id}:{event_type}",
        event_type=event_type,
        payload_snapshot={
            "project_name": project.name,
            "device_name": device.name,
            "actuator_name": actuator.name,
            "actuator_code": actuator.code,
            "feed_level": event.feed_level,
            "free_output_value": event.free_output_value,
            "free_output_unit": event.free_output_unit,
            "scheduled_at": event.scheduled_at.isoformat(),
            "started_at": event.started_at.isoformat() if event.started_at else None,
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
            "status": event.status,
            "failure_reason": event.failure_reason,
        },
    )


async def scan_automatic_feeder_schedules(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    local_now = timestamp.astimezone(ZoneInfo(settings.display_timezone))
    rows = list(
        (
            await db.execute(
                select(AutomaticFeederConfig, Actuator, Device, Project)
                .join(Actuator, Actuator.id == AutomaticFeederConfig.actuator_id)
                .join(Device, Device.id == Actuator.device_id)
                .join(Project, Project.id == Device.project_id)
                .options(selectinload(AutomaticFeederConfig.slots))
                .where(
                    AutomaticFeederConfig.schedule_enabled.is_(True),
                    Actuator.is_enabled.is_(True),
                    Actuator.is_deleted.is_(False),
                    Actuator.removed_at.is_(None),
                    Device.is_enabled.is_(True),
                    Device.is_deleted.is_(False),
                    Project.status == "ACTIVE",
                    Project.is_deleted.is_(False),
                )
            )
        ).all()
    )
    created_count = 0
    for config, actuator, _device, project in rows:
        for slot in config.slots:
            scheduled_at = _scheduled_utc(local_now.date(), slot.feed_time)
            if scheduled_at < _config_created_at_utc(config):
                continue
            elapsed_seconds = (timestamp - scheduled_at).total_seconds()
            if elapsed_seconds < 0:
                continue
            status = (
                FeederEventStatus.SCHEDULED.value
                if elapsed_seconds <= settings.feeder_schedule_grace_seconds
                else FeederEventStatus.MISSED.value
            )
            insert_stmt = (
                pg_insert(AutomaticFeederEvent)
                .values(
                    actuator_id=actuator.id,
                    command_id=None,
                    source=FeederEventSource.SCHEDULE.value,
                    feed_level=config.feed_level,
                    free_output_value=config.free_output_value,
                    free_output_unit=config.free_output_unit,
                    scheduled_at=scheduled_at,
                    status=status,
                    failure_reason=(
                        "SCHEDULE_GRACE_EXCEEDED"
                        if status == FeederEventStatus.MISSED.value
                        else None
                    ),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        AutomaticFeederEvent.actuator_id,
                        AutomaticFeederEvent.scheduled_at,
                    ]
                )
                .returning(AutomaticFeederEvent.id)
            )
            event_id = await db.scalar(insert_stmt)
            if event_id is None:
                continue
            created_count += 1
            if status == FeederEventStatus.MISSED.value:
                event = await db.get(AutomaticFeederEvent, event_id)
                assert event is not None
                await _enqueue_feeder_outcome(
                    db, event=event, event_type="FEEDING_MISSED"
                )
                continue
            command_payload = {
                "feed_level": config.feed_level,
                "free_output_value": config.free_output_value,
                "free_output_unit": config.free_output_unit,
            }
            command = await create_actuator_command(
                db,
                actuator=actuator,
                desired_state=True,
                requested_by_user_id=project.owner_user_id,
                command_type="FEED",
                command_payload=command_payload,
                commit=False,
            )
            event = await db.get(AutomaticFeederEvent, event_id)
            assert event is not None
            event.command_id = command.id
    return created_count


async def create_manual_feeder_event(
    db: AsyncSession,
    *,
    actuator: Actuator,
    command: ActuatorCommand,
) -> AutomaticFeederEvent:
    payload = command.command_payload or {}
    event = AutomaticFeederEvent(
        actuator_id=actuator.id,
        command_id=command.id,
        source=FeederEventSource.MANUAL.value,
        feed_level=str(payload.get("feed_level")),
        free_output_value=payload.get("free_output_value"),
        free_output_unit=payload.get("free_output_unit"),
        scheduled_at=command.requested_at,
        status=FeederEventStatus.SCHEDULED.value,
    )
    db.add(event)
    await db.flush()
    return event


async def mark_feeder_running(
    db: AsyncSession,
    *,
    command_id: int,
    at: datetime | None = None,
) -> bool:
    event = await db.scalar(
        select(AutomaticFeederEvent)
        .where(
            AutomaticFeederEvent.command_id == command_id,
            AutomaticFeederEvent.status == FeederEventStatus.SCHEDULED.value,
        )
        .with_for_update()
    )
    if event is None:
        return False
    event.status = FeederEventStatus.RUNNING.value
    event.started_at = at or datetime.now(UTC)
    return True


async def mark_feeder_completed(
    db: AsyncSession,
    *,
    actuator_id: int,
    at: datetime | None = None,
) -> bool:
    event = await db.scalar(
        select(AutomaticFeederEvent)
        .where(
            AutomaticFeederEvent.actuator_id == actuator_id,
            AutomaticFeederEvent.status == FeederEventStatus.RUNNING.value,
        )
        .order_by(AutomaticFeederEvent.started_at.desc(), AutomaticFeederEvent.id.desc())
        .limit(1)
        .with_for_update()
    )
    if event is None:
        return False
    event.status = FeederEventStatus.COMPLETED.value
    event.ended_at = at or datetime.now(UTC)
    actuator = await db.get(Actuator, actuator_id)
    if actuator is not None:
        actuator.desired_state = False
    await _enqueue_feeder_outcome(
        db, event=event, event_type="FEEDING_COMPLETED"
    )
    return True


async def mark_feeder_failed(
    db: AsyncSession,
    *,
    command_id: int,
    reason: str,
    at: datetime | None = None,
) -> bool:
    event = await db.scalar(
        select(AutomaticFeederEvent)
        .where(
            AutomaticFeederEvent.command_id == command_id,
            AutomaticFeederEvent.status.in_(
                (FeederEventStatus.SCHEDULED.value, FeederEventStatus.RUNNING.value)
            ),
        )
        .with_for_update()
    )
    if event is None:
        return False
    event.status = FeederEventStatus.FAILED.value
    event.ended_at = at or datetime.now(UTC)
    event.failure_reason = reason
    actuator = await db.get(Actuator, event.actuator_id)
    if actuator is not None:
        actuator.desired_state = False
    await _enqueue_feeder_outcome(
        db, event=event, event_type="FEEDING_FAILED"
    )
    return True
