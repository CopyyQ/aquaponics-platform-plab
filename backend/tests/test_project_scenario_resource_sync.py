from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator
from app.models.actuator_model import ActuatorModel
from app.models.device import Device
from app.models.project import Project
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioItem,
)
from app.models.scenario_catalog import ScenarioCatalog
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.user import User
from app.schemas.project_scenario import ProjectScenarioCreate
from app.services.project_scenario_service import (
    clone_project_scenario,
    create_project_scenario,
)
from app.services.project_scenario_sync_service import (
    clone_catalog_to_project_scenario,
    retire_actuator_from_scenarios,
    retire_sensor_from_scenarios,
    sync_new_actuator_to_scenarios,
    sync_new_sensor_to_scenarios,
)
from scripts.seed import CANONICAL_SCENARIO_CATALOG_CODE


async def _context(db):
    project = await db.scalar(
        select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
    )
    admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
    catalog = await db.scalar(
        select(ScenarioCatalog)
        .options(selectinload(ScenarioCatalog.items))
        .where(ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE)
    )
    assert project is not None and admin is not None and catalog is not None
    device = await db.scalar(select(Device).where(Device.project_id == project.id))
    assert device is not None
    return project, device, admin, catalog


async def _clear_scenarios(db, device_id: int) -> None:
    await db.execute(
        delete(ProjectScenario).where(ProjectScenario.device_id == device_id)
    )
    await db.flush()


async def _scenario_triplet(db, device, admin, catalog):
    active = await clone_catalog_to_project_scenario(
        db,
        catalog=catalog,
        device=device,
        actor_id=admin.id,
        name="Catalog A",
    )
    clone = await clone_project_scenario(
        db,
        source=active,
        actor_id=admin.id,
        name="Catalog B",
        description=None,
    )
    blank = await create_project_scenario(
        db,
        device=device,
        actor_id=admin.id,
        payload=ProjectScenarioCreate(name="Blank C"),
    )
    return active, clone, blank


@pytest.mark.asyncio
async def test_new_sensor_is_added_to_all_scenarios_and_only_catalog_provenance_bootstraps() -> None:
    async with AsyncSessionLocal() as db:
        _, device, admin, catalog = await _context(db)
        await _clear_scenarios(db, device.id)
        active, clone, blank = await _scenario_triplet(
            db, device, admin, catalog
        )

        ph = await db.scalar(select(SensorModel).where(SensorModel.code == "PH"))
        ph_catalog_item = next(
            item
            for item in catalog.items
            if item.target_type == "SENSOR" and item.sensor_model_id == ph.id
        )
        assert ph is not None
        suffix = uuid4().hex[:8]
        sensor = Sensor(
            device_id=device.id,
            sensor_model_id=ph.id,
            code=f"SYNC-PH-{suffix}",
            name=f"Runtime PH {suffix}",
            is_enabled=True,
        )
        db.add(sensor)
        await db.flush()

        created = await sync_new_sensor_to_scenarios(
            db,
            device=device,
            sensor=sensor,
            actor_id=admin.id,
        )
        assert created == 3

        rows = list(
            (
                await db.scalars(
                    select(ProjectScenarioItem)
                    .options(selectinload(ProjectScenarioItem.branches))
                    .where(ProjectScenarioItem.sensor_id == sensor.id)
                    .order_by(ProjectScenarioItem.project_scenario_id)
                )
            ).all()
        )
        assert len(rows) == 3
        by_scenario = {row.project_scenario_id: row for row in rows}

        expected_keys = {
            branch["key"]
            for branch in ph_catalog_item.branches
            if branch.get("enabled", True)
        }
        for scenario in (active, clone):
            item = by_scenario[scenario.id]
            assert item.source_scenario_catalog_item_id == ph_catalog_item.id
            assert {branch.branch_key for branch in item.branches} == expected_keys

        blank_item = by_scenario[blank.id]
        assert blank_item.source_scenario_catalog_item_id is None
        assert blank_item.branches == []

        await db.rollback()


@pytest.mark.asyncio
async def test_new_actuator_is_added_to_all_scenarios_and_catalog_clone_preserves_provenance() -> None:
    async with AsyncSessionLocal() as db:
        _, device, admin, catalog = await _context(db)
        await _clear_scenarios(db, device.id)
        active, clone, blank = await _scenario_triplet(
            db, device, admin, catalog
        )

        pump = await db.scalar(
            select(ActuatorModel).where(ActuatorModel.code == "FISH_TANK_PUMP")
        )
        assert pump is not None
        pump_catalog_item = next(
            item
            for item in catalog.items
            if item.target_type == "ACTUATOR" and item.actuator_model_id == pump.id
        )
        suffix = uuid4().hex[:8]
        max_sequence = (
            await db.scalar(
                select(Actuator.sequence_number)
                .where(Actuator.device_id == device.id)
                .order_by(Actuator.sequence_number.desc())
                .limit(1)
            )
            or 0
        )
        actuator = Actuator(
            device_id=device.id,
            actuator_model_id=pump.id,
            sequence_number=max_sequence + 100,
            code=f"SYNC-PUMP-{suffix}",
            name=f"Runtime pump {suffix}",
            is_enabled=True,
        )
        db.add(actuator)
        await db.flush()

        created = await sync_new_actuator_to_scenarios(
            db,
            device=device,
            actuator=actuator,
            actor_id=admin.id,
        )
        assert created == 3

        rows = list(
            (
                await db.scalars(
                    select(ProjectScenarioItem)
                    .options(selectinload(ProjectScenarioItem.branches))
                    .where(ProjectScenarioItem.actuator_id == actuator.id)
                    .order_by(ProjectScenarioItem.project_scenario_id)
                )
            ).all()
        )
        assert len(rows) == 3
        by_scenario = {row.project_scenario_id: row for row in rows}
        expected_keys = {
            branch["key"]
            for branch in pump_catalog_item.branches
            if branch.get("enabled", True)
        }
        for scenario in (active, clone):
            item = by_scenario[scenario.id]
            assert item.source_scenario_catalog_item_id == pump_catalog_item.id
            assert {branch.branch_key for branch in item.branches} == expected_keys
        assert by_scenario[blank.id].branches == []

        await db.rollback()


@pytest.mark.asyncio
async def test_retiring_resource_retires_its_items_and_branches_in_every_scenario() -> None:
    async with AsyncSessionLocal() as db:
        _, device, admin, catalog = await _context(db)
        await _clear_scenarios(db, device.id)
        await _scenario_triplet(db, device, admin, catalog)

        ph = await db.scalar(select(SensorModel).where(SensorModel.code == "PH"))
        pump = await db.scalar(
            select(ActuatorModel).where(ActuatorModel.code == "FISH_TANK_PUMP")
        )
        assert ph is not None and pump is not None
        suffix = uuid4().hex[:8]
        sensor = Sensor(
            device_id=device.id,
            sensor_model_id=ph.id,
            code=f"RET-PH-{suffix}",
            name="Retire PH",
            is_enabled=True,
        )
        max_sequence = (
            await db.scalar(
                select(Actuator.sequence_number)
                .where(Actuator.device_id == device.id)
                .order_by(Actuator.sequence_number.desc())
                .limit(1)
            )
            or 0
        )
        actuator = Actuator(
            device_id=device.id,
            actuator_model_id=pump.id,
            sequence_number=max_sequence + 101,
            code=f"RET-PUMP-{suffix}",
            name="Retire pump",
            is_enabled=True,
        )
        db.add_all([sensor, actuator])
        await db.flush()
        await sync_new_sensor_to_scenarios(
            db, device=device, sensor=sensor, actor_id=admin.id
        )
        await sync_new_actuator_to_scenarios(
            db, device=device, actuator=actuator, actor_id=admin.id
        )

        retired_at = datetime.now(UTC)
        sensor_count = await retire_sensor_from_scenarios(
            db,
            device=device,
            sensor=sensor,
            actor_id=admin.id,
            retired_at=retired_at,
        )
        actuator_count = await retire_actuator_from_scenarios(
            db,
            device=device,
            actuator=actuator,
            actor_id=admin.id,
            retired_at=retired_at,
        )
        assert sensor_count == 3
        assert actuator_count == 3

        items = list(
            (
                await db.scalars(
                    select(ProjectScenarioItem)
                    .options(selectinload(ProjectScenarioItem.branches))
                    .where(
                        (ProjectScenarioItem.sensor_id == sensor.id)
                        | (ProjectScenarioItem.actuator_id == actuator.id)
                    )
                )
            ).all()
        )
        assert len(items) == 6
        assert all(item.retired_at is not None for item in items)
        assert all(
            branch.retired_at is not None
            for item in items
            for branch in item.branches
        )

        await db.rollback()
