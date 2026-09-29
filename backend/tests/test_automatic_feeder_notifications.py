from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.operational_alert import NotificationDelivery, NotificationOutbox
from app.models.project import Project
from app.models.project_settings import (
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.models.user import User
from app.services.notification_outbox_service import (
    enqueue_operational_event,
    evaluate_notification_policy,
    process_notification_outbox,
)
from app.services.telegram_notifier import TelegramDeliveryResult
from tests.session_auth import session_headers


class SuccessfulNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    async def send_message(self, chat_id: str, text: str, *, reply_markup=None):
        self.calls.append((chat_id, text, reply_markup))
        return TelegramDeliveryResult(True, status_code=200)


async def _runtime_project() -> tuple[Project, User]:
    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        assert project is not None and admin is not None
        return project, admin


async def _reset(project_id: int) -> None:
    async with AsyncSessionLocal() as db:
        outbox_ids = select(NotificationOutbox.id).where(NotificationOutbox.project_id == project_id)
        await db.execute(delete(NotificationDelivery).where(NotificationDelivery.outbox_id.in_(outbox_ids)))
        await db.execute(delete(NotificationOutbox).where(NotificationOutbox.project_id == project_id))
        await db.execute(delete(ProjectNotificationRecipient).where(ProjectNotificationRecipient.project_id == project_id))
        await db.execute(delete(ProjectNotificationSettings).where(ProjectNotificationSettings.project_id == project_id))
        await db.commit()


async def _configure(
    project_id: int,
    *,
    enabled: bool = True,
    telegram: bool = True,
    recipient: bool = True,
    recipient_enabled: bool = True,
) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            ProjectNotificationSettings(
                project_id=project_id,
                enabled=enabled,
                in_app_enabled=True,
                telegram_enabled=telegram,
                notify_alert_recovered=True,
            )
        )
        if recipient:
            db.add(
                ProjectNotificationRecipient(
                    project_id=project_id,
                    name="Feeder operator",
                    telegram_chat_id="999001",
                    enabled=recipient_enabled,
                )
            )
        await db.commit()


def _payload(project: Project, event_type: str) -> dict:
    now = datetime(2026, 9, 28, 11, 0, tzinfo=UTC)
    return {
        "event_type": event_type,
        "project_name": project.name,
        "device_name": "Thiết bị Aquaponics",
        "actuator_name": "Máy cho ăn tự động",
        "feed_level": "LEVEL_2",
        "scheduled_at": now.isoformat(),
        "started_at": now.isoformat(),
        "ended_at": now.isoformat(),
        "status": event_type.removeprefix("FEEDING_"),
        "failure_reason": "TIMEOUT" if event_type != "FEEDING_COMPLETED" else None,
    }


@pytest.mark.asyncio
async def test_feeder_system_event_policy_allows_only_terminal_feeder_events() -> None:
    project, _admin = await _runtime_project()
    await _reset(project.id)
    try:
        await _configure(project.id)
        async with AsyncSessionLocal() as db:
            for event_type in ("FEEDING_COMPLETED", "FEEDING_FAILED", "FEEDING_MISSED"):
                assert await evaluate_notification_policy(
                    db,
                    project_id=project.id,
                    source_type="SYSTEM_EVENT",
                    event_type=event_type,
                    risk=None,
                ) is None
            assert await evaluate_notification_policy(
                db,
                project_id=project.id,
                source_type="SYSTEM_EVENT",
                event_type="DEVICE_STATUS",
                risk=None,
            ) == "INCIDENT_ONLY"
    finally:
        await _reset(project.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "telegram", "expected_reason"),
    [(False, True, "NOTIFICATIONS_DISABLED"), (True, False, "TELEGRAM_DISABLED")],
)
async def test_feeder_delivery_respects_project_channel_switches(
    enabled: bool, telegram: bool, expected_reason: str
) -> None:
    project, _admin = await _runtime_project()
    await _reset(project.id)
    try:
        await _configure(project.id, enabled=enabled, telegram=telegram)
        async with AsyncSessionLocal() as db:
            await enqueue_operational_event(
                db,
                project_id=project.id,
                source_key=f"feeder:{uuid4().hex}",
                event_type="FEEDING_FAILED",
                payload_snapshot=_payload(project, "FEEDING_FAILED"),
            )
            await db.commit()
            notifier = SuccessfulNotifier()
            assert await process_notification_outbox(db, notifier=notifier) == 1
            outbox = await db.scalar(
                select(NotificationOutbox).where(NotificationOutbox.project_id == project.id)
            )
            assert outbox is not None
            assert outbox.status == "SKIPPED"
            assert outbox.skip_reason == expected_reason
            assert notifier.calls == []
    finally:
        await _reset(project.id)


@pytest.mark.asyncio
async def test_feeder_outcomes_send_once_and_format_runtime_context() -> None:
    project, _admin = await _runtime_project()
    await _reset(project.id)
    try:
        await _configure(project.id)
        async with AsyncSessionLocal() as db:
            for event_type in ("FEEDING_COMPLETED", "FEEDING_FAILED", "FEEDING_MISSED"):
                source_key = f"feeder-event:{event_type.lower()}"
                await enqueue_operational_event(
                    db,
                    project_id=project.id,
                    source_key=source_key,
                    event_type=event_type,
                    payload_snapshot=_payload(project, event_type),
                )
                if event_type == "FEEDING_COMPLETED":
                    await enqueue_operational_event(
                        db,
                        project_id=project.id,
                        source_key=source_key,
                        event_type=event_type,
                        payload_snapshot=_payload(project, event_type),
                    )
            await db.commit()
            notifier = SuccessfulNotifier()
            assert await process_notification_outbox(db, notifier=notifier) == 3
            assert len(notifier.calls) == 3
            messages = "\n".join(call[1] for call in notifier.calls)
            assert "Máy cho ăn tự động" in messages
            assert "LEVEL_2" in messages
            assert "HOÀN THÀNH" in messages
            assert "THẤT BẠI" in messages
            assert "BỎ LỠ" in messages
            assert "TIMEOUT" in messages
            assert await db.scalar(
                select(func.count(NotificationOutbox.id)).where(
                    NotificationOutbox.project_id == project.id,
                    NotificationOutbox.source_type == "SYSTEM_EVENT",
                )
            ) == 3
    finally:
        await _reset(project.id)


@pytest.mark.asyncio
async def test_disabled_recipient_does_not_receive_feeder_event() -> None:
    project, _admin = await _runtime_project()
    await _reset(project.id)
    try:
        await _configure(project.id, recipient_enabled=False)
        async with AsyncSessionLocal() as db:
            await enqueue_operational_event(
                db,
                project_id=project.id,
                source_key=f"feeder:{uuid4().hex}",
                event_type="FEEDING_COMPLETED",
                payload_snapshot=_payload(project, "FEEDING_COMPLETED"),
            )
            await db.commit()
            notifier = SuccessfulNotifier()
            assert await process_notification_outbox(db, notifier=notifier) == 1
            assert notifier.calls == []
    finally:
        await _reset(project.id)


@pytest.mark.asyncio
async def test_delivery_history_reads_feeder_event_without_incident() -> None:
    project, admin = await _runtime_project()
    await _reset(project.id)
    try:
        await _configure(project.id)
        async with AsyncSessionLocal() as db:
            await enqueue_operational_event(
                db,
                project_id=project.id,
                source_key="feeder-history-test",
                event_type="FEEDING_COMPLETED",
                payload_snapshot=_payload(project, "FEEDING_COMPLETED"),
            )
            await db.commit()
            assert await process_notification_outbox(db, notifier=SuccessfulNotifier()) == 1
        headers = await session_headers(admin)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/aquaponics-systems/{project.public_id}/alert-delivery/history",
                headers=headers,
            )
            assert response.status_code == 200, response.text
            item = next(
                row
                for row in response.json()
                if row["event_type"] == "FEEDING_COMPLETED"
            )
            assert item["incident_id"] is None
            assert item["status"] == "SENT"
    finally:
        await _reset(project.id)


@pytest.mark.asyncio
async def test_runtime_terminal_transitions_enqueue_feeder_system_events() -> None:
    from app.models.actuator import ActuatorCommand
    from app.models.automatic_feeder import AutomaticFeederEvent
    from app.services.actuator_command_service import create_actuator_command
    from app.services.automatic_feeder_runtime_service import (
        create_manual_feeder_event,
        mark_feeder_completed,
        mark_feeder_failed,
        mark_feeder_running,
    )
    from tests.test_automatic_feeder_api import _cleanup_actuator, _make_feeder

    _headers, _project, _device, actuator = await _make_feeder()
    try:
        async with AsyncSessionLocal() as db:
            owner = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
            assert owner is not None
            command = await create_actuator_command(
                db,
                actuator=await db.get(type(actuator), actuator.id),
                desired_state=True,
                requested_by_user_id=owner.id,
                command_type="FEED",
                command_payload={
                    "feed_level": "LEVEL_1",
                    "free_output_value": None,
                    "free_output_unit": None,
                },
                commit=False,
            )
            await create_manual_feeder_event(
                db, actuator=await db.get(type(actuator), actuator.id), command=command
            )
            await db.commit()
            assert await mark_feeder_running(db, command_id=command.id) is True
            assert await mark_feeder_completed(db, actuator_id=actuator.id) is True
            await db.commit()
            completed = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.project_id == _project.id,
                    NotificationOutbox.event_type == "FEEDING_COMPLETED",
                )
            )
            assert completed is not None

            command2 = await create_actuator_command(
                db,
                actuator=await db.get(type(actuator), actuator.id),
                desired_state=True,
                requested_by_user_id=owner.id,
                command_type="FEED",
                command_payload={
                    "feed_level": "LEVEL_1",
                    "free_output_value": None,
                    "free_output_unit": None,
                },
                commit=False,
            )
            await create_manual_feeder_event(
                db, actuator=await db.get(type(actuator), actuator.id), command=command2
            )
            await db.commit()
            assert await mark_feeder_failed(
                db, command_id=command2.id, reason="DEVICE_FAILED"
            ) is True
            await db.commit()
            failed = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.project_id == _project.id,
                    NotificationOutbox.event_type == "FEEDING_FAILED",
                )
            )
            assert failed is not None
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(NotificationDelivery).where(
                    NotificationDelivery.outbox_id.in_(
                        select(NotificationOutbox.id).where(
                            NotificationOutbox.project_id == _project.id
                        )
                    )
                )
            )
            await db.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.project_id == _project.id
                )
            )
            await db.execute(
                delete(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.actuator_id == actuator.id
                )
            )
            await db.execute(
                delete(ActuatorCommand).where(
                    ActuatorCommand.actuator_id == actuator.id
                )
            )
            await db.commit()
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_missed_schedule_enqueues_feeding_missed_notification() -> None:
    from datetime import time

    from app.models.automatic_feeder import (
        AutomaticFeederConfig,
        AutomaticFeederEvent,
        AutomaticFeederScheduleSlot,
    )
    from app.services.automatic_feeder_runtime_service import (
        scan_automatic_feeder_schedules,
    )
    from tests.test_automatic_feeder_api import _cleanup_actuator, _make_feeder

    _headers, project, _device, actuator = await _make_feeder()
    try:
        async with AsyncSessionLocal() as db:
            config = await db.scalar(
                select(AutomaticFeederConfig).where(
                    AutomaticFeederConfig.actuator_id == actuator.id
                )
            )
            assert config is not None
            config.created_at = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
            await db.execute(
                delete(AutomaticFeederScheduleSlot).where(
                    AutomaticFeederScheduleSlot.feeder_config_id == config.id
                )
            )
            db.add(
                AutomaticFeederScheduleSlot(
                    feeder_config_id=config.id,
                    slot_number=1,
                    feed_time=time(8, 0),
                )
            )
            config.schedule_enabled = True
            await db.commit()
            created = await scan_automatic_feeder_schedules(
                db, now=datetime(2026, 9, 29, 1, 3, tzinfo=UTC)
            )
            await db.commit()
            assert created == 1
            outbox = await db.scalar(
                select(NotificationOutbox).where(
                    NotificationOutbox.project_id == project.id,
                    NotificationOutbox.event_type == "FEEDING_MISSED",
                )
            )
            assert outbox is not None
            assert outbox.payload_snapshot["failure_reason"] == "SCHEDULE_GRACE_EXCEEDED"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(NotificationDelivery).where(
                    NotificationDelivery.outbox_id.in_(
                        select(NotificationOutbox.id).where(
                            NotificationOutbox.project_id == project.id
                        )
                    )
                )
            )
            await db.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.project_id == project.id
                )
            )
            await db.execute(
                delete(AutomaticFeederEvent).where(
                    AutomaticFeederEvent.actuator_id == actuator.id
                )
            )
            await db.commit()
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_feeder_project_activity_never_enqueues_telegram_outbox() -> None:
    from app.services.project_activity_service import (
        dispatch_project_activity,
        record_project_activity,
    )
    from tests.test_automatic_feeder_api import _cleanup_actuator, _make_feeder

    _headers, project, _device, actuator = await _make_feeder()
    try:
        async with AsyncSessionLocal() as db:
            admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
            assert admin is not None
            activity = await record_project_activity(
                db,
                project_id=project.id,
                actor=admin,
                action="AUTOMATIC_FEEDER_UPDATED",
                entity_type="ACTUATOR",
                entity_id=actuator.id,
                entity_name=actuator.name,
                changes={"schedule": {"before": ["00:00"], "after": ["08:00"]}},
            )
            await dispatch_project_activity(db, activity_id=activity.id)
            await db.commit()
            assert await db.scalar(
                select(func.count(NotificationOutbox.id)).where(
                    NotificationOutbox.project_id == project.id,
                    NotificationOutbox.source_type == "PROJECT_ACTIVITY",
                )
            ) == 0
    finally:
        await _cleanup_actuator(actuator.id)
