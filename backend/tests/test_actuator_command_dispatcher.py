from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator, ActuatorCommand
from app.models.device import Device
from app.models.user import User
from app.mqtt import publisher
from app.services.actuator_command_dispatch_service import (
    dispatch_due_actuator_commands,
    retry_delay_seconds,
)


async def _seed_commands(
    *,
    now: datetime,
    count: int = 1,
    attempt_count: int = 0,
) -> tuple[int, list[int], str, str]:
    suffix = uuid4().hex[:8].upper()
    async with AsyncSessionLocal() as db:
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        owner = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert device is not None and owner is not None
        actuator = Actuator(
            device_id=device.id,
            sequence_number=9900,
            code=f"OUTBOX-{suffix}",
            name="Actuator outbox regression",
            is_enabled=True,
            desired_state=True,
            reported_state=False,
        )
        db.add(actuator)
        await db.flush()
        commands: list[ActuatorCommand] = []
        for index in range(count):
            command = ActuatorCommand(
                actuator_id=actuator.id,
                desired_state=bool(index % 2 == 0),
                requested_by_user_id=owner.id,
                requested_at=now - timedelta(seconds=count - index),
                status="PENDING",
                publish_attempt_count=attempt_count,
                next_publish_attempt_at=now - timedelta(seconds=1),
            )
            db.add(command)
            commands.append(command)
        await db.commit()
        for command in commands:
            await db.refresh(command)
        return actuator.id, [command.id for command in commands], device.code, actuator.code


async def _cleanup(actuator_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ActuatorCommand).where(ActuatorCommand.actuator_id == actuator_id)
        )
        await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
        await db.commit()


def test_retry_delay_sequence_is_bounded() -> None:
    assert [retry_delay_seconds(attempt) for attempt in range(1, 7)] == [1, 2, 4, 8, 15, 30]
    assert retry_delay_seconds(99) == 30


@pytest.mark.asyncio
async def test_due_command_publishes_and_becomes_published(monkeypatch) -> None:
    now = datetime(2026, 9, 22, 7, 0, tzinfo=UTC)
    actuator_id, command_ids, device_code, actuator_code = await _seed_commands(now=now)
    calls: list[tuple] = []
    monkeypatch.setattr(publisher, "publish_actuator_command", lambda *args: calls.append(args))

    try:
        async with AsyncSessionLocal() as db:
            processed = await dispatch_due_actuator_commands(db, now=now)

        async with AsyncSessionLocal() as db:
            command = await db.get(ActuatorCommand, command_ids[0])
            assert command is not None
            assert processed == 1
            assert command.status == "PUBLISHED"
            assert command.publish_attempt_count == 1
            assert command.published_at == now
            assert command.last_publish_attempt_at == now
            assert command.next_publish_attempt_at is None
            assert command.publish_failure_reason is None
            assert calls == [
                (
                    device_code,
                    command.id,
                    actuator_code,
                    command.desired_state,
                    command.requested_at.isoformat(),
                )
            ]
    finally:
        await _cleanup(actuator_id)


@pytest.mark.asyncio
async def test_failed_publish_schedules_retry(monkeypatch) -> None:
    now = datetime(2026, 9, 22, 7, 5, tzinfo=UTC)
    actuator_id, command_ids, _device_code, _actuator_code = await _seed_commands(now=now)

    def fail_publish(*_args) -> None:
        raise publisher.MqttPublishError("MQTT_CONNECT_ERROR")

    monkeypatch.setattr(publisher, "publish_actuator_command", fail_publish)

    try:
        async with AsyncSessionLocal() as db:
            processed = await dispatch_due_actuator_commands(db, now=now)

        async with AsyncSessionLocal() as db:
            command = await db.get(ActuatorCommand, command_ids[0])
            assert command is not None
            assert processed == 1
            assert command.status == "PENDING"
            assert command.publish_attempt_count == 1
            assert command.last_publish_attempt_at == now
            assert command.next_publish_attempt_at == now + timedelta(seconds=1)
            assert command.publish_failure_reason == "MQTT_CONNECT_ERROR"
            assert command.failed_at is None
    finally:
        await _cleanup(actuator_id)


@pytest.mark.asyncio
async def test_final_failed_attempt_becomes_terminal(monkeypatch) -> None:
    now = datetime(2026, 9, 22, 7, 10, tzinfo=UTC)
    actuator_id, command_ids, _device_code, _actuator_code = await _seed_commands(
        now=now,
        attempt_count=settings.actuator_command_publish_max_attempts - 1,
    )

    monkeypatch.setattr(
        publisher,
        "publish_actuator_command",
        lambda *_args: (_ for _ in ()).throw(publisher.MqttPublishError("MQTT_TIMEOUT")),
    )

    try:
        async with AsyncSessionLocal() as db:
            processed = await dispatch_due_actuator_commands(db, now=now)

        async with AsyncSessionLocal() as db:
            command = await db.get(ActuatorCommand, command_ids[0])
            assert command is not None
            assert processed == 1
            assert command.status == "FAILED"
            assert command.publish_attempt_count == settings.actuator_command_publish_max_attempts
            assert command.failed_at == now
            assert command.next_publish_attempt_at is None
            assert command.publish_failure_reason == "MQTT_TIMEOUT"
            assert command.failure_reason == "MQTT_PUBLISH_RETRIES_EXHAUSTED"
    finally:
        await _cleanup(actuator_id)


@pytest.mark.asyncio
async def test_same_actuator_commands_cannot_publish_out_of_order(monkeypatch) -> None:
    now = datetime(2026, 9, 22, 7, 15, tzinfo=UTC)
    actuator_id, command_ids, _device_code, _actuator_code = await _seed_commands(
        now=now,
        count=2,
    )
    published_ids: list[int] = []

    def capture_publish(_device, command_id, *_args) -> None:
        published_ids.append(command_id)

    monkeypatch.setattr(publisher, "publish_actuator_command", capture_publish)

    try:
        async with AsyncSessionLocal() as db:
            first_processed = await dispatch_due_actuator_commands(db, now=now)

        assert first_processed == 1
        assert published_ids == [command_ids[0]]

        async with AsyncSessionLocal() as db:
            first = await db.get(ActuatorCommand, command_ids[0])
            second = await db.get(ActuatorCommand, command_ids[1])
            assert first is not None and second is not None
            assert first.status == "PUBLISHED"
            assert second.status == "PENDING"
            first.status = "ACKNOWLEDGED"
            first.acknowledged_at = now
            await db.commit()

        async with AsyncSessionLocal() as db:
            second_processed = await dispatch_due_actuator_commands(
                db,
                now=now + timedelta(seconds=1),
            )

        assert second_processed == 1
        assert published_ids == command_ids
    finally:
        await _cleanup(actuator_id)


@pytest.mark.asyncio
async def test_second_worker_skips_locked_command(monkeypatch) -> None:
    now = datetime(2026, 9, 22, 7, 20, tzinfo=UTC)
    actuator_id, command_ids, _device_code, _actuator_code = await _seed_commands(now=now)
    published_ids: list[int] = []
    monkeypatch.setattr(
        publisher,
        "publish_actuator_command",
        lambda _device, command_id, *_args: published_ids.append(command_id),
    )

    try:
        async with AsyncSessionLocal() as lock_db:
            locked = await lock_db.scalar(
                select(ActuatorCommand)
                .where(ActuatorCommand.id == command_ids[0])
                .with_for_update()
            )
            assert locked is not None

            async with AsyncSessionLocal() as worker_db:
                processed = await dispatch_due_actuator_commands(worker_db, now=now)

            assert processed == 0
            assert published_ids == []
            await lock_db.rollback()
    finally:
        await _cleanup(actuator_id)
