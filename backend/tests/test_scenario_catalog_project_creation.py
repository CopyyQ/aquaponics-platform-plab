from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.core.enums import UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.device_template import DeviceTemplate
from app.models.operational_alert import AlertRuleProjectOverride
from app.models.permission import Role
from app.models.project import Project
from app.models.project_scenario import ProjectScenario, ProjectScenarioItem
from app.models.scenario_catalog import ScenarioCatalog, ScenarioCatalogItem
from app.models.sensor import Sensor
from app.models.threshold_alert_config import ThresholdAlertConfig
from app.models.user import User
from app.services.alert_evaluators import EVALUATOR_REGISTRY
from app.services.aquaponics_system_creation_service import (
    DEFAULT_AQUAPONICS_SYSTEM_NAME,
    AquaponicsSystemCreationError,
    create_aquaponics_system,
)
from scripts.seed import (
    CANONICAL_DEVICE_TEMPLATE_CODE,
    CANONICAL_SCENARIO_CATALOG_CODE,
)

EXPECTED_SENSOR_CODES = {
    "NH3", "NO3", "PH", "DO", "TDS", "WATER_TEMPERATURE", "WATER_LEVEL",
    "AIR_TEMPERATURE", "AIR_HUMIDITY", "LIGHT_INTENSITY", "VOLTAGE", "CURRENT",
}
EXPECTED_ACTUATOR_CODES = {
    "FISH_TANK_PUMP", "BIOFILTER_PUMP", "AERATION_PUMP", "FRESH_WATER_VALVE",
    "FILTER_DRAIN_VALVE", "GROW_LIGHT", "WARNING_LIGHT", "WARNING_BUZZER",
}


@pytest.mark.asyncio
async def test_seed_scenario_catalog_covers_all_canonical_hardware() -> None:
    async with AsyncSessionLocal() as db:
        catalog = await db.scalar(
            select(ScenarioCatalog)
            .options(
                selectinload(ScenarioCatalog.items).selectinload(
                    ScenarioCatalogItem.sensor_model
                ),
                selectinload(ScenarioCatalog.items).selectinload(
                    ScenarioCatalogItem.actuator_model
                ),
            )
            .where(ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE)
        )
        assert catalog is not None
        items = list(
            (
                await db.scalars(
                    select(ScenarioCatalogItem).where(
                        ScenarioCatalogItem.scenario_catalog_id == catalog.id
                    )
                )
            ).all()
        )
        assert len(items) == 20

        sensor_codes = {
            item.sensor_model.code
            for item in items
            if item.target_type == "SENSOR"
        }
        actuator_codes = {
            item.actuator_model.code
            for item in items
            if item.target_type == "ACTUATOR"
        }
        assert sensor_codes == EXPECTED_SENSOR_CODES
        assert actuator_codes == EXPECTED_ACTUATOR_CODES

        ph = next(item for item in items if item.sensor_model and item.sensor_model.code == "PH")
        assert ph.is_enabled is True
        assert {branch["key"] for branch in ph.branches} == {"PH_LOW", "PH_HIGH"}

        no3 = next(item for item in items if item.sensor_model and item.sensor_model.code == "NO3")
        assert no3.is_enabled is False
        assert no3.branches == []

        fish_pump = next(
            item
            for item in items
            if item.actuator_model and item.actuator_model.code == "FISH_TANK_PUMP"
        )
        assert fish_pump.is_enabled is True
        assert {branch["key"] for branch in fish_pump.branches} == {"NO_LOAD", "NO_POWER"}


def test_multi_condition_supports_desired_state_and_electrical_evidence() -> None:
    evaluator = EVALUATOR_REGISTRY["MULTI_CONDITION"]
    config = {
        "logic": "AND",
        "desired_state": True,
        "reported_state": None,
        "voltage": {"operator": "EQ", "value": 12},
        "current": {"operator": "EQ", "value": 0},
        "duration_seconds": 0,
    }
    assert evaluator.validate(config) == []
    assert evaluator.evaluate(
        config,
        {
            "desired_state": True,
            "reported_state": False,
            "voltage_v": 12,
            "current_a": 0,
        },
    ).active is True
    assert evaluator.evaluate(
        config,
        {
            "desired_state": False,
            "reported_state": False,
            "voltage_v": 12,
            "current_a": 0,
        },
    ).active is False


@pytest.mark.asyncio
async def test_project_creation_materializes_selected_catalogs_once_per_owner() -> None:
    suffix = uuid4().hex[:10]
    created_owner_id: int | None = None
    created_project_id: int | None = None
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        role = await db.scalar(select(Role).where(Role.code == "OWNER"))
        template = await db.scalar(
            select(DeviceTemplate).where(
                DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE
            )
        )
        catalog = await db.scalar(
            select(ScenarioCatalog)
            .options(
                selectinload(ScenarioCatalog.items).selectinload(
                    ScenarioCatalogItem.sensor_model
                ),
                selectinload(ScenarioCatalog.items).selectinload(
                    ScenarioCatalogItem.actuator_model
                ),
            )
            .where(ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE)
        )
        assert admin and role and template and catalog

        owner = User(
            username=f"scenario-owner-{suffix}",
            password_hash=hash_password("ScenarioOwner@123"),
            full_name="Scenario owner test",
            email=f"scenario-owner-{suffix}@example.test",
            phone_number=f"9{suffix[:9]}",
            address="",
            system_role=UserRole.OWNER,
            role_id=role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add(owner)
        await db.commit()
        await db.refresh(owner)
        created_owner_id = owner.id

        try:
            project = await create_aquaponics_system(
                db,
                owner_user_id=owner.id,
                actor_id=admin.id,
                device_template_id=template.id,
                scenario_catalog_id=catalog.id,
            )
            created_project_id = project.id

            assert project.name == DEFAULT_AQUAPONICS_SYSTEM_NAME == "Hệ thống Aquaponics"
            assert project.device_template_id == template.id
            assert project.scenario_catalog_id == catalog.id

            devices = list(
                (await db.scalars(select(Device).where(Device.project_id == project.id))).all()
            )
            assert len(devices) == 1
            device = devices[0]
            assert device.device_template_id == template.id

            sensors = list(
                (await db.scalars(select(Sensor).where(Sensor.device_id == device.id))).all()
            )
            actuators = list(
                (await db.scalars(select(Actuator).where(Actuator.device_id == device.id))).all()
            )
            assert len(sensors) == 12
            assert len(actuators) == 8

            sensor_ids = [row.id for row in sensors]
            actuator_ids = [row.id for row in actuators]
            legacy_count = int(
                await db.scalar(
                    select(func.count())
                    .select_from(ThresholdAlertConfig)
                    .where(
                        (ThresholdAlertConfig.sensor_id.in_(sensor_ids))
                        | (ThresholdAlertConfig.actuator_id.in_(actuator_ids))
                    )
                )
                or 0
            )
            assert legacy_count == 0

            scenarios = list(
                (
                    await db.scalars(
                        select(ProjectScenario)
                        .options(
                            selectinload(ProjectScenario.items).selectinload(
                                ProjectScenarioItem.branches
                            )
                        )
                        .where(ProjectScenario.project_id == project.id)
                    )
                )
                .unique()
                .all()
            )
            assert len(scenarios) == 1
            scenario = scenarios[0]
            assert scenario.is_active is True
            assert scenario.name == catalog.name
            assert scenario.source_scenario_catalog_id == catalog.id
            assert len(scenario.items) == len(sensors) + len(actuators) == 20

            ph_catalog = next(
                row
                for row in catalog.items
                if row.target_type == "SENSOR"
                and row.sensor_model is not None
                and row.sensor_model.code == "PH"
            )
            ph_sensor = next(
                row for row in sensors if row.sensor_model_id == ph_catalog.sensor_model_id
            )
            ph_item = next(
                row for row in scenario.items if row.sensor_id == ph_sensor.id
            )
            assert ph_item.source_scenario_catalog_item_id == ph_catalog.id
            assert {branch.branch_key for branch in ph_item.branches} == {
                branch["key"]
                for branch in ph_catalog.branches
                if branch.get("enabled", True)
            }

            legacy_rule_count = int(
                await db.scalar(
                    select(func.count(AlertRuleProjectOverride.rule_id)).where(
                        AlertRuleProjectOverride.project_id == project.id
                    )
                )
                or 0
            )
            assert legacy_rule_count == 0

            with pytest.raises(AquaponicsSystemCreationError) as exc_info:
                await create_aquaponics_system(
                    db,
                    owner_user_id=owner.id,
                    actor_id=admin.id,
                    device_template_id=template.id,
                    scenario_catalog_id=catalog.id,
                )
            assert exc_info.value.code == "OWNER_ALREADY_HAS_AQUAPONICS_SYSTEM"
            assert exc_info.value.status_code == 409
        finally:
            if created_project_id is not None:
                await db.execute(
                    delete(ProjectScenario).where(
                        ProjectScenario.project_id == created_project_id
                    )
                )
                device_ids = select(Device.id).where(Device.project_id == created_project_id)
                await db.execute(delete(Sensor).where(Sensor.device_id.in_(device_ids)))
                await db.execute(delete(Actuator).where(Actuator.device_id.in_(device_ids)))
                await db.execute(delete(Device).where(Device.project_id == created_project_id))
                await db.execute(delete(Project).where(Project.id == created_project_id))
            if created_owner_id is not None:
                await db.execute(delete(User).where(User.id == created_owner_id))
            await db.commit()
