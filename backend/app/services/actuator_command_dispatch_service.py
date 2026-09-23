from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.models.actuator import Actuator, ActuatorCommand
from app.models.device import Device
from app.mqtt import publisher


RETRY_DELAYS_SECONDS = (1, 2, 4, 8, 15, 30)
_NON_TERMINAL_STATUSES = ("PENDING", "PUBLISHED")


def retry_delay_seconds(attempt_count: int) -> int:
    index = max(0, min(attempt_count - 1, len(RETRY_DELAYS_SECONDS) - 1))
    return RETRY_DELAYS_SECONDS[index]


def _due_command_query(now: datetime):
    earlier = aliased(ActuatorCommand)
    earlier_non_terminal = exists(
        select(earlier.id).where(
            earlier.actuator_id == ActuatorCommand.actuator_id,
            earlier.status.in_(_NON_TERMINAL_STATUSES),
            or_(
                earlier.requested_at < ActuatorCommand.requested_at,
                and_(
                    earlier.requested_at == ActuatorCommand.requested_at,
                    earlier.id < ActuatorCommand.id,
                ),
            ),
        )
    )
    return (
        select(ActuatorCommand, Actuator, Device)
        .join(Actuator, Actuator.id == ActuatorCommand.actuator_id)
        .join(Device, Device.id == Actuator.device_id)
        .where(
            ActuatorCommand.status == "PENDING",
            or_(
                ActuatorCommand.next_publish_attempt_at.is_(None),
                ActuatorCommand.next_publish_attempt_at <= now,
            ),
            ~earlier_non_terminal,
        )
        .order_by(ActuatorCommand.requested_at, ActuatorCommand.id)
        .limit(1)
        .with_for_update(of=ActuatorCommand, skip_locked=True)
    )


async def dispatch_due_actuator_commands(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> int:
    processed = 0
    max_items = limit or settings.actuator_command_publish_batch_size

    while processed < max_items:
        attempt_at = now or datetime.now(UTC)
        row = (await db.execute(_due_command_query(attempt_at))).first()
        if row is None:
            break

        command, actuator, device = row
        command.publish_attempt_count += 1
        command.last_publish_attempt_at = attempt_at

        failure_code: str | None = None
        try:
            await asyncio.to_thread(
                publisher.publish_actuator_command,
                device.code,
                command.id,
                actuator.code,
                command.desired_state,
                command.requested_at.isoformat(),
            )
        except publisher.MqttPublishError as exc:
            failure_code = exc.code
        except Exception:
            failure_code = "MQTT_PUBLISH_ERROR"

        if failure_code is None:
            command.status = "PUBLISHED"
            command.published_at = attempt_at
            command.next_publish_attempt_at = None
            command.publish_failure_reason = None
        else:
            command.publish_failure_reason = failure_code
            if command.publish_attempt_count >= settings.actuator_command_publish_max_attempts:
                command.status = "FAILED"
                command.failed_at = attempt_at
                command.next_publish_attempt_at = None
                command.failure_reason = "MQTT_PUBLISH_RETRIES_EXHAUSTED"
            else:
                command.next_publish_attempt_at = attempt_at + timedelta(
                    seconds=retry_delay_seconds(command.publish_attempt_count)
                )

        await db.commit()
        processed += 1

    return processed
