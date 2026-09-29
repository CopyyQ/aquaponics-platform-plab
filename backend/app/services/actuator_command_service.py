from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actuator import Actuator, ActuatorCommand


async def create_actuator_command(
    db: AsyncSession,
    *,
    actuator: Actuator,
    desired_state: bool,
    requested_by_user_id: int,
    command_type: str = "SET_STATE",
    command_payload: dict | None = None,
    commit: bool = True,
) -> ActuatorCommand:
    requested_at = datetime.now(UTC)
    command = ActuatorCommand(
        actuator_id=actuator.id,
        desired_state=desired_state,
        command_type=command_type,
        command_payload=dict(command_payload or {}),
        requested_by_user_id=requested_by_user_id,
        requested_at=requested_at,
        status="PENDING",
        publish_attempt_count=0,
        next_publish_attempt_at=requested_at,
    )
    actuator.desired_state = desired_state
    actuator.last_command_at = requested_at
    db.add(command)

    # The HTTP transaction durably records intent only. MQTT delivery is
    # performed by the outbox dispatcher so transient broker outages cannot
    # turn a successfully persisted command into a request-path failure.
    if commit:
        await db.commit()
        await db.refresh(command)
    else:
        await db.flush()
    return command
