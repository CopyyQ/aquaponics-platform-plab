from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import delete, func, select, update

from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator, ActuatorCommand
from app.models.automatic_feeder import (
    AutomaticFeederConfig,
    AutomaticFeederEvent,
    AutomaticFeederScheduleSlot,
)
from app.models.device import Device
from app.models.operational_alert import NotificationDelivery, NotificationOutbox
from app.services.automatic_feeder_runtime_service import (
    mark_feeder_completed,
    mark_feeder_failed,
    mark_feeder_running,
    scan_automatic_feeder_schedules,
)
from tests.test_automatic_feeder_api import _cleanup_actuator, _make_feeder


async def _prepare_feeder(*, schedule_enabled: bool = True) -> tuple[int, int, int]:
    _headers, _project, device, actuator = await _make_feeder()
    async with AsyncSessionLocal() as db:
        config = await db.scalar(
            select(AutomaticFeederConfig).where(
                AutomaticFeederConfig.actuator_id == actuator.id
            )
        )
        assert config is not None
        config.created_at = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
        config.schedule_enabled = schedule_enabled
        await db.execute(
            delete(AutomaticFeederScheduleSlot).where(
                AutomaticFeederScheduleSlot.feeder_config_id == config.id
            )
        )
        for number, value in enumerate((time(8), time(12), time(18)), start=1):
            db.add(
                AutomaticFeederScheduleSlot(
                    feeder_config_id=config.id,
                    slot_number=number,
                    feed_time=value,
                )
            )
        await db.commit()
        return actuator.id, device.id, config.id


async def _cleanup_feeder(actuator_id: int) -> None:
    async with AsyncSessionLocal() as db:
        event_ids = list(
            (
                await db.scalars(
                    select(AutomaticFeederEvent.id).where(
                        AutomaticFeederEvent.actuator_id == actuator_id
                    )
                )
            ).all()
        )
        if event_ids:
            idempotency_keys = [
                f"system-event:feeder-event:{event_id}:{event_type}"
                for event_id in event_ids
                for event_type in (
                    "FEEDING_COMPLETED",
                    "FEEDING_FAILED",
                    "FEEDING_MISSED",
                )
            ]
            outbox_ids = select(NotificationOutbox.id).where(
                NotificationOutbox.idempotency_key.in_(idempotency_keys)
            )
            await db.execute(
                delete(NotificationDelivery).where(
                    NotificationDelivery.outbox_id.in_(outbox_ids)
                )
            )
            await db.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.idempotency_key.in_(idempotency_keys)
                )
            )
        await db.execute(
            delete(AutomaticFeederEvent).where(
                AutomaticFeederEvent.actuator_id == actuator_id
            )
        )
        await db.execute(
            delete(ActuatorCommand).where(ActuatorCommand.actuator_id == actuator_id)
        )
        await db.commit()
    await _cleanup_actuator(actuator_id)


@pytest.mark.asyncio
async def test_due_schedule_creates_exactly_one_feed_event_and_command() -> None:
    actuator_id, _device_id, _config_id = await _prepare_feeder()
    now = datetime(2026, 9, 29, 1, 0, 30, tzinfo=UTC)  # 08:00:30 Asia/Ho_Chi_Minh
    try:
        async with AsyncSessionLocal() as db:
            created = await scan_automatic_feeder_schedules(db, now=now)
            await db.commit()
            created_again = await scan_automatic_feeder_schedules(db, now=now)
            await db.commit()
        assert created == 1
        assert created_again == 0

        async with AsyncSessionLocal() as db:
            events = list(
                (
                    await db.scalars(
                        select(AutomaticFeederEvent).where(
                            AutomaticFeederEvent.actuator_id == actuator_id
                        )
                    )
                ).all()
            )
            commands = list(
                (
                    await db.scalars(
                        select(ActuatorCommand).where(
                            ActuatorCommand.actuator_id == actuator_id
                        )
                    )
                ).all()
            )
            assert len(events) == 1
            assert events[0].status == "SCHEDULED"
            assert events[0].source == "SCHEDULE"
            assert len(commands) == 1
            assert commands[0].command_type == "FEED"
            assert commands[0].command_payload["feed_level"] == "LEVEL_1"
            assert events[0].command_id == commands[0].id
    finally:
        await _cleanup_feeder(actuator_id)


@pytest.mark.asyncio
async def test_past_grace_becomes_missed_without_command() -> None:
    actuator_id, _device_id, _config_id = await _prepare_feeder()
    now = datetime(2026, 9, 29, 1, 3, 0, tzinfo=UTC)  # 08:03 local, grace=120s
    try:
        async with AsyncSessionLocal() as db:
            created = await scan_automatic_feeder_schedules(db, now=now)
            await db.commit()
        assert created == 1
        async with AsyncSessionLocal() as db:
            event = await db.scalar(
                select(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.actuator_id == actuator_id
                )
            )
            command_count = await db.scalar(
                select(func.count(ActuatorCommand.id)).where(
                    ActuatorCommand.actuator_id == actuator_id
                )
            )
            assert event is not None
            assert event.status == "MISSED"
            assert event.command_id is None
            assert command_count == 0
    finally:
        await _cleanup_feeder(actuator_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["schedule", "actuator", "device"])
async def test_disabled_feeder_paths_do_not_schedule(target: str) -> None:
    actuator_id, device_id, _config_id = await _prepare_feeder(
        schedule_enabled=target != "schedule"
    )
    try:
        async with AsyncSessionLocal() as db:
            if target == "actuator":
                await db.execute(
                    update(Actuator).where(Actuator.id == actuator_id).values(is_enabled=False)
                )
            elif target == "device":
                await db.execute(
                    update(Device).where(Device.id == device_id).values(is_enabled=False)
                )
            await db.commit()
            created = await scan_automatic_feeder_schedules(
                db, now=datetime(2026, 9, 29, 1, 0, 30, tzinfo=UTC)
            )
            await db.commit()
            assert created == 0
    finally:
        if target == "device":
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Device).where(Device.id == device_id).values(is_enabled=True)
                )
                await db.commit()
        await _cleanup_feeder(actuator_id)


@pytest.mark.asyncio
async def test_feeder_runtime_lifecycle_running_completed_and_failed() -> None:
    actuator_id, _device_id, _config_id = await _prepare_feeder()
    now = datetime(2026, 9, 29, 1, 0, 30, tzinfo=UTC)
    try:
        async with AsyncSessionLocal() as db:
            await scan_automatic_feeder_schedules(db, now=now)
            await db.commit()
            event = await db.scalar(
                select(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.actuator_id == actuator_id
                )
            )
            assert event is not None and event.command_id is not None
            command_id = event.command_id

        async with AsyncSessionLocal() as db:
            assert await mark_feeder_running(db, command_id=command_id, at=now) is True
            await db.commit()
            event = await db.get(AutomaticFeederEvent, event.id)
            assert event is not None and event.status == "RUNNING"

        async with AsyncSessionLocal() as db:
            assert await mark_feeder_completed(db, actuator_id=actuator_id, at=now) is True
            await db.commit()
            event = await db.get(AutomaticFeederEvent, event.id)
            actuator = await db.get(Actuator, actuator_id)
            assert event is not None and event.status == "COMPLETED"
            assert actuator is not None and actuator.desired_state is False

        # A terminal event cannot be rewritten as FAILED.
        async with AsyncSessionLocal() as db:
            assert (
                await mark_feeder_failed(
                    db,
                    command_id=command_id,
                    reason="TIMEOUT",
                    at=now,
                )
                is False
            )
    finally:
        await _cleanup_feeder(actuator_id)


@pytest.mark.asyncio
async def test_manual_feed_command_creates_manual_runtime_event() -> None:
    import httpx

    from app.main import app

    headers, project, device, actuator = await _make_feeder()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers, json={"command_type": "FEED"})
            assert response.status_code == 202, response.text
            command_id = response.json()["command_id"]

        async with AsyncSessionLocal() as db:
            event = await db.scalar(
                select(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.command_id == command_id
                )
            )
            assert event is not None
            assert event.source == "MANUAL"
            assert event.status == "SCHEDULED"
            assert event.feed_level == "LEVEL_1"
    finally:
        await _cleanup_feeder(actuator.id)


@pytest.mark.asyncio
async def test_feed_command_ack_marks_runtime_running(monkeypatch) -> None:
    import json

    import httpx

    from app.main import app
    from app.mqtt.handlers import handle_command_ack

    async def no_notification(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.mqtt.handlers.dispatch_actuator_command_transition",
        no_notification,
    )
    headers, project, device, actuator = await _make_feeder()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers, json={"command_type": "FEED"})
            assert response.status_code == 202, response.text
            command_id = response.json()["command_id"]

        await handle_command_ack(
            device.code,
            json.dumps(
                {
                    "command_id": command_id,
                    "actuator_code": actuator.code,
                    "reported_state": True,
                    "status": "ACKNOWLEDGED",
                    "sent_at": datetime.now(UTC).isoformat(),
                }
            ).encode(),
        )
        async with AsyncSessionLocal() as db:
            event = await db.scalar(
                select(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.command_id == command_id
                )
            )
            assert event is not None
            assert event.status == "RUNNING"
            assert event.started_at is not None
    finally:
        await _cleanup_feeder(actuator.id)


@pytest.mark.asyncio
async def test_feed_command_timeout_marks_runtime_failed(monkeypatch) -> None:
    import httpx

    from app.core.config import settings
    from app.jobs.actuator_command_timeout import timeout_actuator_commands
    from app.main import app

    async def no_notification(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.jobs.actuator_command_timeout.dispatch_actuator_command_transition",
        no_notification,
    )
    headers, project, device, actuator = await _make_feeder()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    now = datetime(2026, 9, 29, 2, 0, tzinfo=UTC)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers, json={"command_type": "FEED"})
            assert response.status_code == 202, response.text
            command_id = response.json()["command_id"]

        async with AsyncSessionLocal() as db:
            command = await db.get(ActuatorCommand, command_id)
            assert command is not None
            command.status = "PUBLISHED"
            command.published_at = now - timedelta(
                seconds=settings.actuator_command_timeout_seconds + 1
            )
            await db.commit()

        assert await timeout_actuator_commands(now=now) == 1
        async with AsyncSessionLocal() as db:
            event = await db.scalar(
                select(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.command_id == command_id
                )
            )
            refreshed = await db.get(Actuator, actuator.id)
            assert event is not None
            assert event.status == "FAILED"
            assert event.failure_reason == "TIMEOUT"
            assert refreshed is not None and refreshed.desired_state is False
    finally:
        await _cleanup_feeder(actuator.id)


@pytest.mark.asyncio
async def test_periodic_off_after_running_completes_feed(monkeypatch) -> None:
    import json

    import httpx

    from app.main import app
    from app.mqtt.handlers import handle_command_ack, handle_status

    async def no_notification(*_args, **_kwargs) -> None:
        return None

    async def no_project_scenarios(*_args, **_kwargs) -> bool:
        return False

    async def no_alert_eval(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.mqtt.handlers.dispatch_actuator_command_transition",
        no_notification,
    )
    monkeypatch.setattr(
        "app.mqtt.handlers.device_uses_project_scenarios",
        no_project_scenarios,
    )
    monkeypatch.setattr(
        "app.mqtt.handlers.evaluate_alert_scenarios_for_actuator",
        no_alert_eval,
    )

    headers, project, device, actuator = await _make_feeder()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers, json={"command_type": "FEED"})
            assert response.status_code == 202, response.text
            command_id = response.json()["command_id"]

        started_at = datetime.now(UTC)
        await handle_command_ack(
            device.code,
            json.dumps(
                {
                    "command_id": command_id,
                    "actuator_code": actuator.code,
                    "reported_state": True,
                    "status": "ACKNOWLEDGED",
                    "sent_at": started_at.isoformat(),
                }
            ).encode(),
        )
        await handle_status(
            device.code,
            json.dumps(
                {
                    "status": "ONLINE",
                    "sent_at": (started_at + timedelta(seconds=1)).isoformat(),
                    "actuators": [
                        {"actuator_code": actuator.code, "state": False}
                    ],
                }
            ).encode(),
        )

        async with AsyncSessionLocal() as db:
            event = await db.scalar(
                select(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.command_id == command_id
                )
            )
            refreshed = await db.get(Actuator, actuator.id)
            assert event is not None
            assert event.status == "COMPLETED"
            assert event.ended_at is not None
            assert refreshed is not None
            assert refreshed.desired_state is False
            assert refreshed.reported_state is False
    finally:
        await _cleanup_feeder(actuator.id)
