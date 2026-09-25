from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.models.actuator_model import ActuatorModel
from app.models.device_template import DeviceTemplate
from app.models.permission import Permission, Role
from app.models.scenario_catalog import ScenarioCatalog
from app.models.sensor import SensorModel
from scripts.seed import (
    CANONICAL_ACTUATOR_MODEL_CODES,
    CANONICAL_DEVICE_TEMPLATE_CODE,
    CANONICAL_SCENARIO_CATALOG_CODE,
    CANONICAL_SENSOR_MODEL_CODES,
    DEFAULT_SENSOR_SCENARIOS,
    seed,
)


def test_seed_catalog_does_not_depend_on_historical_migrations() -> None:
    source = Path("scripts/seed.py").read_text(encoding="utf-8")
    assert "alembic/versions" not in source
    assert "importlib.util" not in source


def test_canonical_sensor_thresholds_match_business_source() -> None:
    ph = {branch["key"]: branch for branch in DEFAULT_SENSOR_SCENARIOS["PH"]["branches"]}
    water_level = {
        branch["key"]: branch
        for branch in DEFAULT_SENSOR_SCENARIOS["WATER_LEVEL"]["branches"]
    }
    fish_tank_water_level = {
        branch["key"]: branch
        for branch in DEFAULT_SENSOR_SCENARIOS["WATER_LEVELW2"]["branches"]
    }

    assert ph["PH_LOW"]["condition_config"]["operator"] == "LT"
    assert ph["PH_LOW"]["condition_config"]["value"] == 6
    assert ph["PH_HIGH"]["condition_config"]["operator"] == "GT"
    assert ph["PH_HIGH"]["condition_config"]["value"] == 7.5
    assert water_level["WATER_LEVEL_LOW"]["condition_config"]["operator"] == "LT"
    assert water_level["WATER_LEVEL_LOW"]["condition_config"]["value"] == 60
    assert water_level["WATER_LEVEL_LOW"]["message"] == "Mức nước bể lọc vi sinh thấp hơn 60%."
    assert fish_tank_water_level["WATER_LEVEL_LOW"]["condition_config"]["operator"] == "LT"
    assert fish_tank_water_level["WATER_LEVEL_LOW"]["condition_config"]["value"] == 60
    assert fish_tank_water_level["WATER_LEVEL_LOW"]["message"] == "Mức nước bể cá thấp hơn 60%."


@pytest.mark.asyncio
async def test_seed_is_idempotent_for_v1_catalogs_and_rbac() -> None:
    await seed()
    await seed()

    async with AsyncSessionLocal() as db:
        sensor_codes = set((await db.scalars(select(SensorModel.code))).all())
        actuator_codes = set((await db.scalars(select(ActuatorModel.code))).all())
        assert sensor_codes == set(CANONICAL_SENSOR_MODEL_CODES)
        assert actuator_codes == set(CANONICAL_ACTUATOR_MODEL_CODES)

        template_count = int(
            await db.scalar(
                select(func.count())
                .select_from(DeviceTemplate)
                .where(
                    DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE,
                    DeviceTemplate.is_deleted.is_(False),
                )
            )
            or 0
        )
        scenario_count = int(
            await db.scalar(
                select(func.count())
                .select_from(ScenarioCatalog)
                .where(
                    ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE,
                    ScenarioCatalog.is_deleted.is_(False),
                )
            )
            or 0
        )
        assert template_count == 1
        assert scenario_count == 1

        template = await db.scalar(
            select(DeviceTemplate).where(
                DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE
            )
        )
        assert template is not None
        assert "13 loại cảm biến" in (template.description or "")
        assert "số instance thực tế" in (template.description or "")

        role_codes = set((await db.scalars(select(Role.code))).all())
        assert role_codes == {
            UserRole.ADMIN.value,
            UserRole.OWNER.value,
            UserRole.VIEWER.value,
        }

        duplicate_permission_codes = list(
            (
                await db.execute(
                    select(Permission.code, func.count(Permission.id))
                    .group_by(Permission.code)
                    .having(func.count(Permission.id) > 1)
                )
            ).all()
        )
        assert duplicate_permission_codes == []

        permission_codes = set((await db.scalars(select(Permission.code))).all())
        for required in (
            "users.read",
            "aquaponics_systems.manage_all",
            "actuators.commands.create",
            "project_scenarios.read",
            "project_scenarios.create",
            "project_scenarios.update",
            "project_scenarios.delete",
            "project_scenarios.activate",
            "permissions.read",
            "roles.permissions.update",
            "role_assignments.update",
            "user_permissions.update",
        ):
            assert required in permission_codes
