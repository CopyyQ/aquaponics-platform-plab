from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.models.operational_alert import NotificationOutbox, OperationalIncident
from app.models.project import Project
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.telemetry import TelemetryReading
from app.models.user import User
from app.schemas.project_scenario import ProjectScenarioBranchUpdate
from app.services.project_scenario_evaluator import evaluate_active_sensor_scenario
from app.services.project_scenario_service import (
    activate_project_scenario,
    update_project_scenario_branch,
)


async def _context(db):
    project = await db.scalar(
        select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
    )
    admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
    ph = await db.scalar(select(SensorModel).where(SensorModel.code == "PH"))
    assert project is not None and admin is not None and ph is not None
    device = await db.scalar(select(Device).where(Device.project_id == project.id))
    assert device is not None
    return project, device, admin, ph


async def _reset_scenario_state(db, device: Device) -> None:
    ids = select(OperationalIncident.id).where(
        OperationalIncident.device_id == device.id,
        OperationalIncident.project_scenario_id.is_not(None),
    )
    await db.execute(delete(NotificationOutbox).where(NotificationOutbox.incident_id.in_(ids)))
    await db.execute(
        delete(OperationalIncident).where(
            OperationalIncident.device_id == device.id,
            OperationalIncident.project_scenario_id.is_not(None),
        )
    )
    await db.execute(
        delete(ProjectScenario).where(ProjectScenario.device_id == device.id)
    )
    await db.flush()


async def _sensor(db, device: Device, model: SensorModel) -> Sensor:
    suffix = uuid4().hex[:8]
    sensor = Sensor(
        device_id=device.id,
        sensor_model_id=model.id,
        code=f"EVAL-PH-{suffix}",
        name=f"Evaluator pH {suffix}",
        is_enabled=True,
    )
    db.add(sensor)
    await db.flush()
    return sensor


async def _scenario(
    db,
    *,
    project: Project,
    device: Device,
    sensor: Sensor,
    actor: User,
    name: str,
    active: bool,
    threshold: float,
    duration_seconds: int = 0,
    message: str = "Cảnh báo",
) -> tuple[ProjectScenario, ProjectScenarioBranch]:
    scenario = ProjectScenario(
        project_id=project.id,
        device_id=device.id,
        name=name,
        is_active=active,
        created_by=actor.id,
        updated_by=actor.id,
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
        branch_key=f"HIGH_{uuid4().hex[:6]}",
        name=f"{name} pH cao",
        evaluator_type="THRESHOLD",
        condition_config={"operator": "GT", "value": threshold},
        duration_seconds=duration_seconds,
        business_risk_level="HIGH",
        message_template=message,
        consequence="Ảnh hưởng cá",
        recommended_action="Kiểm tra nước",
        is_enabled=True,
        position=0,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(branch)
    await db.flush()
    return scenario, branch


@pytest.mark.asyncio
async def test_only_active_scenario_creates_incident_and_switch_maps_future_alerts_to_new_scenario() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin, ph = await _context(db)
        await _reset_scenario_state(db, device)
        sensor = await _sensor(db, device, ph)
        scenario_a, branch_a = await _scenario(
            db,
            project=project,
            device=device,
            sensor=sensor,
            actor=admin,
            name="A",
            active=True,
            threshold=7.2,
            message="A message",
        )
        scenario_b, branch_b = await _scenario(
            db,
            project=project,
            device=device,
            sensor=sensor,
            actor=admin,
            name="B",
            active=False,
            threshold=8.0,
            message="B message",
        )
        t0 = datetime.now(UTC)
        db.add(
            TelemetryReading(
                sensor_id=sensor.id,
                recorded_at=t0,
                received_at=t0,
                value=7.5,
            )
        )
        await db.flush()

        changed = await evaluate_active_sensor_scenario(
            db,
            device=device,
            sensor=sensor,
            value=7.5,
            quality="VALID",
            recorded_at=t0,
            received_at=t0,
        )
        assert len(changed) == 1
        incident_a = changed[0]
        assert incident_a.project_scenario_id == scenario_a.id
        assert incident_a.project_scenario_branch_id == branch_a.id
        assert incident_a.status == "OPEN"
        assert incident_a.trigger_snapshot["scenario_name"] == "A"
        assert incident_a.trigger_snapshot["message_template"] == "A message"
        assert await db.scalar(
            select(OperationalIncident.id).where(
                OperationalIncident.project_scenario_branch_id == branch_b.id
            )
        ) is None

        activated_at = t0 + timedelta(seconds=1)
        result = await activate_project_scenario(
            db,
            device=device,
            target=scenario_b,
            actor=admin,
            activated_at=activated_at,
        )
        assert result.closed_incident_count == 1
        await db.refresh(incident_a)
        assert incident_a.status == "RESOLVED"
        assert incident_a.resolution_reason == "SCENARIO_CHANGED"
        assert (
            await db.scalar(
                select(NotificationOutbox.id).where(
                    NotificationOutbox.incident_id == incident_a.id,
                    NotificationOutbox.event_type == "RECOVERED",
                )
            )
            is None
        )

        changed_b = await evaluate_active_sensor_scenario(
            db,
            device=device,
            sensor=sensor,
            value=8.5,
            quality="VALID",
            recorded_at=activated_at + timedelta(seconds=1),
            received_at=activated_at + timedelta(seconds=1),
        )
        assert len(changed_b) == 1
        incident_b = changed_b[0]
        assert incident_b.project_scenario_id == scenario_b.id
        assert incident_b.project_scenario_branch_id == branch_b.id
        assert incident_b.trigger_snapshot["scenario_name"] == "B"
        assert incident_b.trigger_snapshot["message_template"] == "B message"

        await db.rollback()


@pytest.mark.asyncio
async def test_semantic_branch_edit_reconciles_but_message_edit_preserves_open_incident_snapshot() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin, ph = await _context(db)
        await _reset_scenario_state(db, device)
        sensor = await _sensor(db, device, ph)
        _, branch = await _scenario(
            db,
            project=project,
            device=device,
            sensor=sensor,
            actor=admin,
            name="Active",
            active=True,
            threshold=7.2,
            message="Original message",
        )
        now = datetime.now(UTC)
        db.add(
            TelemetryReading(
                sensor_id=sensor.id,
                recorded_at=now,
                received_at=now,
                value=7.5,
            )
        )
        await db.flush()
        incident = (
            await evaluate_active_sensor_scenario(
                db,
                device=device,
                sensor=sensor,
                value=7.5,
                quality="VALID",
                recorded_at=now,
                received_at=now,
            )
        )[0]
        original_snapshot = dict(incident.trigger_snapshot)

        await update_project_scenario_branch(
            db,
            branch=branch,
            actor_id=admin.id,
            payload=ProjectScenarioBranchUpdate(
                message_template="New message only"
            ),
        )
        await db.refresh(incident)
        assert incident.status == "OPEN"
        assert incident.trigger_snapshot == original_snapshot

        await update_project_scenario_branch(
            db,
            branch=branch,
            actor_id=admin.id,
            payload=ProjectScenarioBranchUpdate(
                condition_config={"operator": "GT", "value": 8.0}
            ),
        )
        await db.refresh(incident)
        assert incident.status == "RESOLVED"
        assert incident.resolution_reason == "SCENARIO_CONFIGURATION_CHANGED"
        assert incident.trigger_snapshot == original_snapshot
        assert (
            await db.scalar(
                select(NotificationOutbox.id).where(
                    NotificationOutbox.incident_id == incident.id,
                    NotificationOutbox.event_type == "RECOVERED",
                )
            )
            is None
        )

        await db.rollback()
