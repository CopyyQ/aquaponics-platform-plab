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
from app.services.project_scenario_service import activate_project_scenario


async def _context(db):
    project = await db.scalar(
        select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
    )
    admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
    ph = await db.scalar(select(SensorModel).where(SensorModel.code == "PH"))
    assert project is not None and admin is not None and ph is not None
    device = await db.scalar(select(Device).where(Device.project_id == project.id))
    assert device is not None
    incident_ids = select(OperationalIncident.id).where(
        OperationalIncident.device_id == device.id,
        OperationalIncident.project_scenario_id.is_not(None),
    )
    await db.execute(
        delete(NotificationOutbox).where(
            NotificationOutbox.incident_id.in_(incident_ids)
        )
    )
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
    return project, device, admin, ph


async def _sensor(db, device, ph):
    suffix = uuid4().hex[:8]
    sensor = Sensor(
        device_id=device.id,
        sensor_model_id=ph.id,
        code=f"ACT-PH-{suffix}",
        name=f"Activation pH {suffix}",
        is_enabled=True,
    )
    db.add(sensor)
    await db.flush()
    return sensor


async def _scenario_with_item(
    db,
    *,
    project,
    device,
    sensor,
    admin,
    name,
    active,
):
    scenario = ProjectScenario(
        project_id=project.id,
        device_id=device.id,
        name=name,
        is_active=active,
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
    return scenario, item


@pytest.mark.asyncio
async def test_switch_resolves_pending_open_and_acknowledged_without_recovery_notification() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin, ph = await _context(db)
        sensor = await _sensor(db, device, ph)
        scenario_a, item_a = await _scenario_with_item(
            db,
            project=project,
            device=device,
            sensor=sensor,
            admin=admin,
            name="A",
            active=True,
        )
        scenario_b, _ = await _scenario_with_item(
            db,
            project=project,
            device=device,
            sensor=sensor,
            admin=admin,
            name="B",
            active=False,
        )
        now = datetime.now(UTC)
        incidents = []
        for position, status in enumerate(("PENDING", "OPEN", "ACKNOWLEDGED")):
            branch = ProjectScenarioBranch(
                project_scenario_item_id=item_a.id,
                branch_key=f"STATE_{status}",
                name=status,
                evaluator_type="THRESHOLD",
                condition_config={"operator": "GT", "value": 7.0 + position},
                duration_seconds=60 if status == "PENDING" else 0,
                business_risk_level="HIGH",
                is_enabled=True,
                position=position,
                created_by=admin.id,
                updated_by=admin.id,
            )
            db.add(branch)
            await db.flush()
            incident = OperationalIncident(
                project_id=project.id,
                rule_id=None,
                rule_revision_id=None,
                device_id=device.id,
                sensor_id=sensor.id,
                actuator_id=None,
                project_scenario_id=scenario_a.id,
                project_scenario_item_id=item_a.id,
                project_scenario_branch_id=branch.id,
                context_key=f"scenario_branch:{branch.id}",
                status=status,
                technical_severity="WARNING",
                business_risk_level_snapshot="HIGH",
                started_at=now - timedelta(seconds=30),
                opened_at=(
                    None if status == "PENDING" else now - timedelta(seconds=20)
                ),
                acknowledged_at=(now if status == "ACKNOWLEDGED" else None),
                last_triggered_at=now,
                occurrence_count=1,
                trigger_snapshot={"snapshot_version": 1},
            )
            db.add(incident)
            incidents.append(incident)
        await db.flush()

        result = await activate_project_scenario(
            db,
            device=device,
            target=scenario_b,
            actor=admin,
            activated_at=now,
        )
        assert result.closed_incident_count == 3
        for incident in incidents:
            await db.refresh(incident)
            assert incident.status == "RESOLVED"
            assert incident.resolution_reason == "SCENARIO_CHANGED"
            assert incident.resolved_at == now
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


@pytest.mark.asyncio
async def test_activation_restarts_duration_timer_from_switch_time_using_latest_value() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin, ph = await _context(db)
        sensor = await _sensor(db, device, ph)
        scenario_a, _ = await _scenario_with_item(
            db,
            project=project,
            device=device,
            sensor=sensor,
            admin=admin,
            name="A",
            active=True,
        )
        scenario_b, item_b = await _scenario_with_item(
            db,
            project=project,
            device=device,
            sensor=sensor,
            admin=admin,
            name="B",
            active=False,
        )
        branch_b = ProjectScenarioBranch(
            project_scenario_item_id=item_b.id,
            branch_key="B_DELAY",
            name="B delayed",
            evaluator_type="THRESHOLD",
            condition_config={"operator": "GT", "value": 7.2},
            duration_seconds=60,
            business_risk_level="HIGH",
            is_enabled=True,
            position=0,
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(branch_b)
        t0 = datetime.now(UTC)
        db.add(
            TelemetryReading(
                sensor_id=sensor.id,
                recorded_at=t0,
                received_at=t0,
                value=7.8,
            )
        )
        await db.flush()

        activated_at = t0 + timedelta(seconds=30)
        result = await activate_project_scenario(
            db,
            device=device,
            target=scenario_b,
            actor=admin,
            activated_at=activated_at,
        )
        assert result.previous_scenario_id == scenario_a.public_id
        assert result.reevaluated_sensor_count == 1

        incident = await db.scalar(
            select(OperationalIncident).where(
                OperationalIncident.project_scenario_branch_id == branch_b.id,
                OperationalIncident.status == "PENDING",
            )
        )
        assert incident is not None
        assert incident.started_at == activated_at
        assert incident.opened_at is None

        await db.rollback()
