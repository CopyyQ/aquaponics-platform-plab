from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.jobs import actuator_command_timeout
from app.models.actuator import Actuator, ActuatorCommand
from app.models.device import Device
from app.models.user import User


@pytest.mark.asyncio
async def test_timeout_only_applies_to_published_commands(monkeypatch) -> None:
    now = datetime(2026, 9, 22, 8, 0, tzinfo=UTC)
    suffix = uuid4().hex[:8].upper()
    actuator_id: int | None = None
    command_ids: list[int] = []

    async def no_audit(*_args, **_kwargs):
        return None

    async def no_notification(*_args, **_kwargs):
        return None

    monkeypatch.setattr(actuator_command_timeout, "write_audit", no_audit)
    monkeypatch.setattr(
        actuator_command_timeout,
        "dispatch_actuator_command_transition",
        no_notification,
    )

    async with AsyncSessionLocal() as db:
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        owner = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert device is not None and owner is not None
        actuator = Actuator(
            device_id=device.id,
            sequence_number=9910,
            code=f"TIMEOUT-{suffix}",
            name="Actuator timeout regression",
            is_enabled=True,
            desired_state=True,
            reported_state=False,
        )
        db.add(actuator)
        await db.flush()
        actuator_id = actuator.id

        pending_old = ActuatorCommand(
            actuator_id=actuator.id,
            desired_state=True,
            requested_by_user_id=owner.id,
            requested_at=now - timedelta(minutes=10),
            status="PENDING",
            publish_attempt_count=1,
            next_publish_attempt_at=now + timedelta(seconds=30),
        )
        published_old = ActuatorCommand(
            actuator_id=actuator.id,
            desired_state=True,
            requested_by_user_id=owner.id,
            requested_at=now - timedelta(minutes=5),
            status="PUBLISHED",
            published_at=now - timedelta(minutes=2),
            publish_attempt_count=1,
        )
        published_recent = ActuatorCommand(
            actuator_id=actuator.id,
            desired_state=False,
            requested_by_user_id=owner.id,
            requested_at=now - timedelta(seconds=30),
            status="PUBLISHED",
            published_at=now - timedelta(seconds=10),
            publish_attempt_count=1,
        )
        db.add_all([pending_old, published_old, published_recent])
        await db.commit()
        for command in (pending_old, published_old, published_recent):
            await db.refresh(command)
            command_ids.append(command.id)

    try:
        timed_out = await actuator_command_timeout.timeout_actuator_commands(now=now)

        async with AsyncSessionLocal() as db:
            rows = {
                command.id: command
                for command in (
                    await db.scalars(
                        select(ActuatorCommand).where(ActuatorCommand.id.in_(command_ids))
                    )
                ).all()
            }

        assert timed_out == 1
        assert rows[command_ids[0]].status == "PENDING"
        assert rows[command_ids[0]].timed_out_at is None
        assert rows[command_ids[1]].status == "TIMEOUT"
        assert rows[command_ids[1]].timed_out_at == now
        assert rows[command_ids[2]].status == "PUBLISHED"
        assert rows[command_ids[2]].timed_out_at is None
    finally:
        async with AsyncSessionLocal() as db:
            if actuator_id is not None:
                await db.execute(
                    delete(ActuatorCommand).where(ActuatorCommand.actuator_id == actuator_id)
                )
                await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
                await db.commit()
