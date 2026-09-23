from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.models.operational_alert import (
    NotificationDelivery,
    NotificationOutbox,
    OperationalIncident,
)
from app.models.project import Project
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.project_settings import (
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.user import User
from app.schemas.project_scenario import ProjectScenarioBranchUpdate
from app.services.notification_outbox_service import process_notification_outbox
from app.services.project_scenario_evaluator import evaluate_active_sensor_scenario
from app.services.project_scenario_service import update_project_scenario_branch
from app.services.telegram_notifier import TelegramDeliveryResult


class CapturingNotifier:
    configured = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send_message(
        self,
        chat_id: str,
        text: str,
        **_kwargs: object,
    ) -> TelegramDeliveryResult:
        self.calls.append((chat_id, text))
        return TelegramDeliveryResult(sent=True, status_code=200)


async def _context(db):
    project = await db.scalar(
        select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
    )
    admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
    model = await db.scalar(select(SensorModel).where(SensorModel.code == "PH"))
    assert project is not None and admin is not None and model is not None
    device = await db.scalar(select(Device).where(Device.project_id == project.id))
    assert device is not None
    return project, device, admin, model


async def _reset(db, project: Project, device: Device) -> None:
    incident_ids = select(OperationalIncident.id).where(
        OperationalIncident.project_id == project.id
    )
    await db.execute(
        delete(NotificationDelivery).where(
            NotificationDelivery.incident_id.in_(incident_ids)
        )
    )
    await db.execute(
        delete(NotificationOutbox).where(NotificationOutbox.project_id == project.id)
    )
    await db.execute(
        delete(OperationalIncident).where(
            OperationalIncident.project_id == project.id
        )
    )
    await db.execute(
        delete(ProjectNotificationRecipient).where(
            ProjectNotificationRecipient.project_id == project.id
        )
    )
    await db.execute(
        delete(ProjectNotificationSettings).where(
            ProjectNotificationSettings.project_id == project.id
        )
    )
    await db.execute(
        delete(ProjectScenario).where(ProjectScenario.device_id == device.id)
    )
    await db.flush()


async def _open_scenario_incident(
    db,
    *,
    project: Project,
    device: Device,
    admin: User,
    model: SensorModel,
) -> tuple[Sensor, ProjectScenarioBranch, OperationalIncident, NotificationOutbox]:
    suffix = uuid4().hex[:8].upper()
    sensor = Sensor(
        device_id=device.id,
        sensor_model_id=model.id,
        code=f"TG-PH-{suffix}",
        name="pH bể cá Telegram",
        is_enabled=True,
    )
    db.add(sensor)
    await db.flush()

    scenario = ProjectScenario(
        project_id=project.id,
        device_id=device.id,
        name="Mùa nóng",
        description="Kịch bản kiểm thử Telegram",
        is_active=True,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(scenario)
    await db.flush()

    item = ProjectScenarioItem(
        project_scenario_id=scenario.id,
        target_type="SENSOR",
        sensor_id=sensor.id,
        actuator_id=None,
        name=sensor.name,
        is_enabled=True,
    )
    db.add(item)
    await db.flush()

    branch = ProjectScenarioBranch(
        project_scenario_item_id=item.id,
        branch_key=f"HIGH_{suffix}",
        name="pH cao mùa nóng",
        evaluator_type="THRESHOLD",
        condition_config={"operator": "GT", "value": 7.2},
        duration_seconds=0,
        business_risk_level="HIGH",
        message_template="pH đang vượt mức của mùa nóng",
        consequence="Cá bị stress",
        recommended_action="Kiểm tra và thay nước",
        is_enabled=True,
        position=0,
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(branch)
    await db.flush()

    now = datetime.now(UTC)
    changed = await evaluate_active_sensor_scenario(
        db,
        device=device,
        sensor=sensor,
        value=7.6,
        quality="VALID",
        recorded_at=now,
        received_at=now,
    )
    assert len(changed) == 1
    incident = changed[0]
    outbox = await db.scalar(
        select(NotificationOutbox).where(
            NotificationOutbox.incident_id == incident.id,
            NotificationOutbox.event_type == "OPEN",
        )
    )
    assert outbox is not None
    return sensor, branch, incident, outbox


@pytest.mark.asyncio
async def test_project_scenario_telegram_uses_scenario_snapshot_content() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin, model = await _context(db)
        await _reset(db, project, device)
        sensor, _, incident, outbox = await _open_scenario_incident(
            db,
            project=project,
            device=device,
            admin=admin,
            model=model,
        )
        db.add_all(
            [
                ProjectNotificationSettings(
                    project_id=project.id,
                    enabled=True,
                    in_app_enabled=True,
                    telegram_enabled=True,
                    notify_alert_recovered=True,
                ),
                ProjectNotificationRecipient(
                    project_id=project.id,
                    name="Operator scenario",
                    telegram_chat_id="scenario-chat",
                    enabled=True,
                ),
            ]
        )
        await db.commit()

        notifier = CapturingNotifier()
        assert await process_notification_outbox(db, notifier=notifier) == 1
        assert len(notifier.calls) == 1
        message = notifier.calls[0][1]
        assert "Kịch bản: Mùa nóng" in message
        assert "Nhánh: pH cao mùa nóng" in message
        assert "Điều kiện: > 7,2" in message
        assert "pH đang vượt mức của mùa nóng" in message
        assert "Cá bị stress" in message
        assert "Kiểm tra và thay nước" in message
        assert outbox.payload_snapshot["scenario_name"] == "Mùa nóng"
        assert incident.trigger_snapshot["condition_config"]["value"] == 7.2

        sensor_id = sensor.id
        await _reset(db, project, device)
        await db.execute(delete(Sensor).where(Sensor.id == sensor_id))
        await db.commit()


@pytest.mark.asyncio
async def test_project_scenario_outbox_and_incident_snapshot_remain_immutable_after_branch_edit() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin, model = await _context(db)
        await _reset(db, project, device)
        sensor, branch, incident, outbox = await _open_scenario_incident(
            db,
            project=project,
            device=device,
            admin=admin,
            model=model,
        )
        original_incident_snapshot = dict(incident.trigger_snapshot)
        original_outbox_snapshot = dict(outbox.payload_snapshot)

        await update_project_scenario_branch(
            db,
            branch=branch,
            actor_id=admin.id,
            payload=ProjectScenarioBranchUpdate(
                message_template="Thông điệp mới không được sửa lịch sử",
                business_risk_level="VERY_HIGH",
            ),
        )
        await db.flush()

        assert incident.trigger_snapshot == original_incident_snapshot
        assert outbox.payload_snapshot == original_outbox_snapshot
        assert outbox.payload_snapshot["condition_config"]["value"] == 7.2
        assert (
            outbox.payload_snapshot["message_template"]
            == "pH đang vượt mức của mùa nóng"
        )

        sensor_id = sensor.id
        await _reset(db, project, device)
        await db.execute(delete(Sensor).where(Sensor.id == sensor_id))
        await db.commit()


@pytest.mark.asyncio
async def test_repeated_scenario_violation_creates_one_incident_one_open_outbox_and_one_delivery() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin, model = await _context(db)
        await _reset(db, project, device)
        sensor, _, incident, _ = await _open_scenario_incident(
            db,
            project=project,
            device=device,
            admin=admin,
            model=model,
        )

        for _ in range(20):
            now = datetime.now(UTC)
            await evaluate_active_sensor_scenario(
                db,
                device=device,
                sensor=sensor,
                value=7.6,
                quality="VALID",
                recorded_at=now,
                received_at=now,
            )

        assert (
            int(
                await db.scalar(
                    select(func.count(OperationalIncident.id)).where(
                        OperationalIncident.project_scenario_branch_id
                        == incident.project_scenario_branch_id
                    )
                )
                or 0
            )
            == 1
        )
        assert (
            int(
                await db.scalar(
                    select(func.count(NotificationOutbox.id)).where(
                        NotificationOutbox.incident_id == incident.id,
                        NotificationOutbox.event_type == "OPEN",
                    )
                )
                or 0
            )
            == 1
        )

        db.add_all(
            [
                ProjectNotificationSettings(
                    project_id=project.id,
                    enabled=True,
                    in_app_enabled=True,
                    telegram_enabled=True,
                    notify_alert_recovered=True,
                ),
                ProjectNotificationRecipient(
                    project_id=project.id,
                    name="Operator dedupe",
                    telegram_chat_id="dedupe-chat",
                    enabled=True,
                ),
            ]
        )
        await db.commit()

        notifier = CapturingNotifier()
        assert await process_notification_outbox(db, notifier=notifier) == 1
        assert len(notifier.calls) == 1
        assert (
            int(
                await db.scalar(
                    select(func.count(NotificationDelivery.id)).where(
                        NotificationDelivery.incident_id == incident.id,
                        NotificationDelivery.status == "SENT",
                    )
                )
                or 0
            )
            == 1
        )

        sensor_id = sensor.id
        await _reset(db, project, device)
        await db.execute(delete(Sensor).where(Sensor.id == sensor_id))
        await db.commit()
