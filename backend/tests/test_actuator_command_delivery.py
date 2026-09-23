import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.api.v1 import aquaponics_systems
from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator, ActuatorCommand, ActuatorStateHistory
from app.models.device import Device
from app.models.project import Project
from app.models.user import User
from app.mqtt import publisher
from app.mqtt.handlers import handle_command_ack
from app.schemas.actuator import ActuatorCommandCreate

@pytest.mark.asyncio
async def test_create_actuator_command_enqueues_pending_without_publishing(monkeypatch) -> None:
    suffix = uuid4().hex[:8].upper()
    published: list[tuple] = []
    actuator_id: int | None = None
    command_id: int | None = None

    def fake_publish(*args) -> None:
        published.append(args)

    monkeypatch.setattr(publisher, "publish_actuator_command", fake_publish)

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        owner = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert project is not None and device is not None and owner is not None
        actuator = Actuator(
            device_id=device.id,
            sequence_number=9801,
            code=f"CMD-PUMP-{suffix}",
            name="Bơm command regression",
            is_enabled=True,
            desired_state=False,
            reported_state=False,
        )
        db.add(actuator)
        await db.commit()
        await db.refresh(actuator)
        actuator_id = actuator.id

        try:
            result = await aquaponics_systems.create_actuator_command(
                project.public_id,
                device.public_id,
                actuator.public_id,
                ActuatorCommandCreate(desired_state=True),
                db,
                owner,
            )
            command_id = result["command_id"]
            await db.refresh(actuator)

            command = await db.get(ActuatorCommand, command_id)
            assert command is not None
            assert result["status"] == "PENDING"
            assert actuator.desired_state is True
            assert command.status == "PENDING"
            assert command.publish_attempt_count == 0
            assert command.next_publish_attempt_at == command.requested_at
            assert published == []
        finally:
            if actuator_id is not None:
                await db.execute(
                    delete(ActuatorCommand).where(ActuatorCommand.actuator_id == actuator_id)
                )
                await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
                await db.commit()


@pytest.mark.asyncio
async def test_broker_failure_cannot_fail_request_path(monkeypatch) -> None:
    suffix = uuid4().hex[:8].upper()
    actuator_id: int | None = None

    def fail_publish(*_args) -> None:
        raise AssertionError("request path must not publish to MQTT")

    monkeypatch.setattr(publisher, "publish_actuator_command", fail_publish)

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        owner = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert project is not None and device is not None and owner is not None
        actuator = Actuator(
            device_id=device.id,
            sequence_number=9802,
            code=f"CMD-FAIL-{suffix}",
            name="Bơm durable enqueue regression",
            is_enabled=True,
            desired_state=False,
            reported_state=False,
        )
        db.add(actuator)
        await db.commit()
        await db.refresh(actuator)
        actuator_id = actuator.id

        try:
            result = await aquaponics_systems.create_actuator_command(
                project.public_id,
                device.public_id,
                actuator.public_id,
                ActuatorCommandCreate(desired_state=True),
                db,
                owner,
            )

            command = await db.get(ActuatorCommand, result["command_id"])
            assert command is not None
            assert result["status"] == "PENDING"
            assert command.status == "PENDING"
            assert command.failed_at is None
            assert command.failure_reason is None
        finally:
            if actuator_id is not None:
                await db.execute(
                    delete(ActuatorCommand).where(ActuatorCommand.actuator_id == actuator_id)
                )
                await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
                await db.commit()


@pytest.mark.asyncio
async def test_terminal_command_ignores_late_ack(monkeypatch) -> None:
    suffix = uuid4().hex[:8].upper()
    actuator_id: int | None = None
    command_id: int | None = None

    async def no_notification(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.mqtt.handlers.dispatch_actuator_command_transition",
        no_notification,
    )

    async with AsyncSessionLocal() as db:
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        owner = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert device is not None and owner is not None
        actuator = Actuator(
            device_id=device.id,
            sequence_number=9803,
            code=f"LATE-ACK-{suffix}",
            name="Actuator late ACK regression",
            is_enabled=True,
            desired_state=True,
            reported_state=False,
        )
        db.add(actuator)
        await db.flush()
        command = ActuatorCommand(
            actuator_id=actuator.id,
            desired_state=True,
            reported_state=None,
            status="TIMEOUT",
            requested_by_user_id=owner.id,
            requested_at=datetime.now(UTC) - timedelta(minutes=2),
            timed_out_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        db.add(command)
        await db.commit()
        await db.refresh(actuator)
        await db.refresh(command)
        actuator_id = actuator.id
        command_id = command.id

    try:
        await handle_command_ack(
            "CODEX-TEST-DEVICE",
            json.dumps(
                {
                    "command_id": command_id,
                    "actuator_code": f"LATE-ACK-{suffix}",
                    "reported_state": True,
                    "status": "ACKNOWLEDGED",
                    "sent_at": datetime.now(UTC).isoformat(),
                }
            ).encode(),
        )

        async with AsyncSessionLocal() as db:
            command = await db.get(ActuatorCommand, command_id)
            assert command is not None
            assert command.status == "TIMEOUT"
            assert command.acknowledged_at is None
            assert command.reported_state is None
    finally:
        async with AsyncSessionLocal() as db:
            if actuator_id is not None:
                await db.execute(
                    delete(ActuatorStateHistory).where(
                        ActuatorStateHistory.actuator_id == actuator_id
                    )
                )
                await db.execute(
                    delete(ActuatorCommand).where(
                        ActuatorCommand.actuator_id == actuator_id
                    )
                )
                await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
                await db.commit()


def test_actuator_command_openapi_does_not_treat_broker_outage_as_request_failure() -> None:
    from app.main import app

    path = (
        "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}"
        "/actuators/{actuator_id}/commands"
    )
    responses = app.openapi()["paths"][path]["post"]["responses"]

    assert "503" not in responses
