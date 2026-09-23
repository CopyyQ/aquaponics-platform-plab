from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.models.operational_alert import OperationalIncident
from app.models.project import Project
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.user import User


async def runtime_context(db):
    project = await db.scalar(
        select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
    )
    admin = await db.scalar(
        select(User).where(User.system_role == UserRole.ADMIN)
    )
    assert project is not None and admin is not None
    await db.refresh(project, attribute_names=["devices"])
    assert project.devices
    return project, project.devices[0], admin


@pytest.mark.asyncio
async def test_one_active_project_scenario_per_device_is_db_enforced() -> None:
    async with AsyncSessionLocal() as db:
        project, device, actor = await runtime_context(db)
        db.add(
            ProjectScenario(
                project_id=project.id,
                device_id=device.id,
                name=f"A-{uuid4().hex[:8]}",
                is_active=True,
                created_by=actor.id,
            )
        )
        await db.flush()

        db.add(
            ProjectScenario(
                project_id=project.id,
                device_id=device.id,
                name=f"B-{uuid4().hex[:8]}",
                is_active=True,
                created_by=actor.id,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()


@pytest.mark.asyncio
async def test_project_scenario_item_requires_exactly_one_runtime_resource() -> None:
    async with AsyncSessionLocal() as db:
        project, device, actor = await runtime_context(db)
        scenario = ProjectScenario(
            project_id=project.id,
            device_id=device.id,
            name=f"ITEM-CHECK-{uuid4().hex[:8]}",
            is_active=False,
            created_by=actor.id,
        )
        db.add(scenario)
        await db.flush()

        db.add(
            ProjectScenarioItem(
                project_scenario_id=scenario.id,
                target_type="SENSOR",
                sensor_id=None,
                actuator_id=None,
                name="invalid",
                is_enabled=True,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()


@pytest.mark.asyncio
async def test_one_active_incident_per_project_scenario_branch_is_db_enforced() -> None:
    async with AsyncSessionLocal() as db:
        project, device, actor = await runtime_context(db)
        sensor = await db.scalar(
            select(Sensor).where(
                Sensor.device_id == device.id,
                Sensor.is_deleted.is_(False),
            )
        )
        if sensor is None:
            model = await db.scalar(
                select(SensorModel).where(SensorModel.code == "PH")
            )
            assert model is not None
            sensor = Sensor(
                device_id=device.id,
                sensor_model_id=model.id,
                code=f"PERSIST-{uuid4().hex[:8]}",
                name="Persistence test sensor",
                is_enabled=True,
            )
            db.add(sensor)
            await db.flush()

        scenario = ProjectScenario(
            project_id=project.id,
            device_id=device.id,
            name=f"INCIDENT-CHECK-{uuid4().hex[:8]}",
            is_active=False,
            created_by=actor.id,
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
            branch_key="high",
            name="High",
            evaluator_type="THRESHOLD",
            condition_config={"operator": "GT", "value": 7.5},
            duration_seconds=0,
            business_risk_level="HIGH",
            is_enabled=True,
            position=0,
            created_by=actor.id,
        )
        db.add(branch)
        await db.flush()

        now = datetime.now(UTC)
        db.add(
            OperationalIncident(
                project_id=project.id,
                rule_id=None,
                rule_revision_id=None,
                device_id=device.id,
                sensor_id=sensor.id,
                actuator_id=None,
                project_scenario_id=scenario.id,
                project_scenario_item_id=item.id,
                project_scenario_branch_id=branch.id,
                context_key=f"scenario_branch:{branch.id}:one",
                status="OPEN",
                technical_severity="WARNING",
                business_risk_level_snapshot="HIGH",
                started_at=now,
                opened_at=now,
                last_triggered_at=now,
                trigger_snapshot={"snapshot_version": 1},
            )
        )
        await db.flush()

        db.add(
            OperationalIncident(
                project_id=project.id,
                rule_id=None,
                rule_revision_id=None,
                device_id=device.id,
                sensor_id=sensor.id,
                actuator_id=None,
                project_scenario_id=scenario.id,
                project_scenario_item_id=item.id,
                project_scenario_branch_id=branch.id,
                context_key=f"scenario_branch:{branch.id}:two",
                status="PENDING",
                technical_severity="WARNING",
                business_risk_level_snapshot="HIGH",
                started_at=now,
                last_triggered_at=now,
                trigger_snapshot={"snapshot_version": 1},
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
