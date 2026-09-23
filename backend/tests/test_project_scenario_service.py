from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.enums import UserRole
from app.core.exceptions import ApplicationError
from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator
from app.models.actuator_model import ActuatorModel
from app.models.device import Device
from app.models.project import Project
from app.models.project_scenario import ProjectScenarioItem
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.user import User
from app.schemas.project_scenario import (
    ProjectScenarioBranchCreate,
    ProjectScenarioCreate,
    ProjectScenarioMetadataUpdate,
)
from app.services.project_scenario_service import (
    clone_project_scenario,
    create_project_scenario,
    create_project_scenario_branch,
    get_project_scenario,
    retire_project_scenario,
    scenario_detail_read,
    update_project_scenario_metadata,
)


async def _runtime_context(db):
    project = await db.scalar(
        select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
    )
    admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
    assert project is not None and admin is not None
    device = await db.scalar(select(Device).where(Device.project_id == project.id))
    assert device is not None
    return project, device, admin


async def _add_resources(db, device: Device):
    sensor_model = await db.scalar(select(SensorModel).order_by(SensorModel.id))
    actuator_model = await db.scalar(select(ActuatorModel).order_by(ActuatorModel.id))
    assert sensor_model is not None and actuator_model is not None
    suffix = uuid4().hex[:8]
    sensor = Sensor(
        device_id=device.id,
        sensor_model_id=sensor_model.id,
        code=f"SVC-S-{suffix}",
        name=f"Sensor {suffix}",
        is_enabled=True,
    )
    actuator = Actuator(
        device_id=device.id,
        actuator_model_id=actuator_model.id,
        sequence_number=int(suffix[:4], 16),
        code=f"SVC-A-{suffix}",
        name=f"Actuator {suffix}",
        is_enabled=True,
    )
    db.add_all([sensor, actuator])
    await db.flush()
    return sensor, actuator


@pytest.mark.asyncio
async def test_blank_scenario_contains_all_current_resources_without_branches() -> None:
    async with AsyncSessionLocal() as db:
        _, device, admin = await _runtime_context(db)
        sensor, actuator = await _add_resources(db, device)

        scenario = await create_project_scenario(
            db,
            device=device,
            actor_id=admin.id,
            payload=ProjectScenarioCreate(
                name="Bảo trì",
                description="Kịch bản trống",
                clone_from_scenario_id=None,
            ),
        )

        by_sensor = {
            item.sensor_id: item
            for item in scenario.items
            if item.target_type == "SENSOR"
        }
        by_actuator = {
            item.actuator_id: item
            for item in scenario.items
            if item.target_type == "ACTUATOR"
        }
        assert sensor.id in by_sensor
        assert actuator.id in by_actuator
        assert all(item.branches == [] for item in scenario.items)
        assert scenario.is_active is False

        detail = scenario_detail_read(scenario)
        assert detail.name == "Bảo trì"
        assert any(item.resource.id == sensor.public_id for item in detail.sensors)
        assert any(item.resource.id == actuator.public_id for item in detail.actuators)


@pytest.mark.asyncio
async def test_clone_is_a_deep_independent_copy_of_items_and_branches() -> None:
    async with AsyncSessionLocal() as db:
        _, device, admin = await _runtime_context(db)
        sensor, _ = await _add_resources(db, device)
        source = await create_project_scenario(
            db,
            device=device,
            actor_id=admin.id,
            payload=ProjectScenarioCreate(name="Nguồn"),
        )
        source_item = next(item for item in source.items if item.sensor_id == sensor.id)
        source_branch = await create_project_scenario_branch(
            db,
            item=source_item,
            actor_id=admin.id,
            payload=ProjectScenarioBranchCreate(
                name="pH cao",
                evaluator_type="THRESHOLD",
                condition_config={"operator": "GT", "value": 7.5},
                duration_seconds=60,
                business_risk_level="HIGH",
                message_template="Cảnh báo nguồn",
                consequence="Ảnh hưởng nguồn",
                recommended_action="Khắc phục nguồn",
                is_enabled=True,
                position=2,
            ),
        )

        clone = await clone_project_scenario(
            db,
            source=source,
            actor_id=admin.id,
            name="Mùa nóng",
            description="Bản sao độc lập",
        )
        clone_item = next(item for item in clone.items if item.sensor_id == sensor.id)
        assert clone.id != source.id
        assert clone.cloned_from_scenario_id == source.id
        assert clone.is_active is False
        assert clone_item.id != source_item.id
        assert len(clone_item.branches) == 1
        clone_branch = clone_item.branches[0]
        assert clone_branch.id != source_branch.id
        assert clone_branch.condition_config == {"operator": "GT", "value": 7.5}
        assert clone_branch.duration_seconds == 60

        clone_branch.condition_config["value"] = 8.2
        clone_branch.message_template = "Cảnh báo clone"
        assert source_branch.condition_config["value"] == 7.5
        assert source_branch.message_template == "Cảnh báo nguồn"


@pytest.mark.asyncio
async def test_active_scenario_cannot_be_retired_but_metadata_can_be_updated() -> None:
    async with AsyncSessionLocal() as db:
        _, device, admin = await _runtime_context(db)
        scenario = await create_project_scenario(
            db,
            device=device,
            actor_id=admin.id,
            payload=ProjectScenarioCreate(name="Đang dùng"),
        )
        scenario.is_active = True
        await db.flush()

        updated = await update_project_scenario_metadata(
            db,
            scenario=scenario,
            actor_id=admin.id,
            payload=ProjectScenarioMetadataUpdate(
                name="Đang dùng - mới",
                description="Mô tả mới",
            ),
        )
        assert updated.name == "Đang dùng - mới"
        assert updated.description == "Mô tả mới"
        assert updated.is_active is True

        with pytest.raises(ApplicationError) as exc_info:
            await retire_project_scenario(
                db,
                scenario=scenario,
                actor_id=admin.id,
                retired_at=datetime.now(UTC),
            )
        assert exc_info.value.code == "ACTIVE_SCENARIO_CANNOT_BE_DELETED"
        assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_scenario_lookup_is_scoped_to_device() -> None:
    async with AsyncSessionLocal() as db:
        project, device, admin = await _runtime_context(db)
        scenario = await create_project_scenario(
            db,
            device=device,
            actor_id=admin.id,
            payload=ProjectScenarioCreate(name="Device A"),
        )
        other = Device(
            project_id=project.id,
            code=f"OTHER-{uuid4().hex[:8]}",
            name="Other device",
            is_enabled=True,
        )
        db.add(other)
        await db.flush()

        with pytest.raises(ApplicationError) as exc_info:
            await get_project_scenario(
                db,
                device=other,
                public_id=scenario.public_id,
            )
        assert exc_info.value.code == "PROJECT_SCENARIO_NOT_FOUND"
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_invalid_branch_configuration_is_rejected() -> None:
    async with AsyncSessionLocal() as db:
        _, device, admin = await _runtime_context(db)
        sensor, _ = await _add_resources(db, device)
        scenario = await create_project_scenario(
            db,
            device=device,
            actor_id=admin.id,
            payload=ProjectScenarioCreate(name="Validation"),
        )
        item: ProjectScenarioItem = next(
            row for row in scenario.items if row.sensor_id == sensor.id
        )

        with pytest.raises(ApplicationError) as exc_info:
            await create_project_scenario_branch(
                db,
                item=item,
                actor_id=admin.id,
                payload=ProjectScenarioBranchCreate(
                    name="Sai",
                    evaluator_type="THRESHOLD",
                    condition_config={"operator": "GT"},
                    duration_seconds=0,
                    business_risk_level="HIGH",
                ),
            )
        assert exc_info.value.code == "SCENARIO_BRANCH_INVALID"
        assert exc_info.value.status_code == 422
