import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.actuator import Actuator, ActuatorCommand
from app.models.device import Device
from app.services.audit_service import write_audit
from app.services.project_notification_service import dispatch_actuator_command_transition

logger = logging.getLogger(__name__)


async def timeout_actuator_commands(*, now: datetime | None = None) -> int:
    timestamp = now or datetime.now(UTC)
    cutoff = timestamp - timedelta(seconds=settings.actuator_command_timeout_seconds)
    async with async_session_factory() as db:
        rows = list((await db.execute(
            select(ActuatorCommand, Actuator, Device)
            .join(Actuator, Actuator.id == ActuatorCommand.actuator_id)
            .join(Device, Device.id == Actuator.device_id)
            .where(
                ActuatorCommand.status == "PUBLISHED",
                ActuatorCommand.published_at.is_not(None),
                ActuatorCommand.published_at < cutoff,
            )
            .with_for_update(of=ActuatorCommand, skip_locked=True)
        )).all())
        timed_out_at = timestamp
        for command, actuator, device in rows:
            command.status = "TIMEOUT"
            command.timed_out_at = timed_out_at
            await write_audit(
                db,
                user_id=command.requested_by_user_id,
                project_id=device.project_id,
                action="ACTUATOR_COMMAND_TIMEOUT",
                entity_type="ACTUATOR",
                entity_id=actuator.id,
                description="Lệnh điều khiển quá thời gian chờ xác nhận",
                new_data={"display_name": actuator.name, "desired_state": command.desired_state, "reported_state": command.reported_state},
            )
        await db.commit()
        for command, _actuator, _device in rows:
            await dispatch_actuator_command_transition(db, command_id=command.id, transition="TIMEOUT")
        if rows:
            logger.warning("event=actuator_command_timed_out count=%s", len(rows))
        return len(rows)
