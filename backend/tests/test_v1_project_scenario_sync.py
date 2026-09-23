from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.models.operational_alert import (
    AlertRule,
    AlertRuleProjectOverride,
    AlertRuleRevision,
    AlertRuleSensorOverride,
)
from app.models.project import Project
from app.models.project_scenario import ProjectScenario, ProjectScenarioBranch, ProjectScenarioItem
from app.models.scenario_catalog import ScenarioCatalog, ScenarioCatalogItem
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.user import User
from scripts.seed import CANONICAL_SCENARIO_CATALOG_CODE
from scripts.sync_v1_project_scenarios import (
    _backfill_device,
    _ensure_v1_project_scenario_schema,
)


async def _fixture_context(db):
    project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
    admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
    catalog = await db.scalar(
        select(ScenarioCatalog).where(
            ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE
        )
    )
    ph_model = await db.scalar(select(SensorModel).where(SensorModel.code == "PH"))
    assert project is not None and admin is not None and catalog is not None
    assert ph_model is not None
    ph_item = await db.scalar(
        select(ScenarioCatalogItem).where(
            ScenarioCatalogItem.scenario_catalog_id == catalog.id,
            ScenarioCatalogItem.target_type == "SENSOR",
            ScenarioCatalogItem.sensor_model_id == ph_model.id,
        )
    )
    assert ph_item is not None
    project.scenario_catalog_id = catalog.id
    return project, admin, catalog, ph_model, ph_item


async def _device_with_sensor(db, *, project: Project, model: SensorModel, suffix: str):
    device = Device(
        project_id=project.id,
        code=f"MIG-{suffix}",
        name=f"Migration {suffix}",
        is_enabled=True,
    )
    db.add(device)
    await db.flush()
    sensor = Sensor(
        device_id=device.id,
        sensor_model_id=model.id,
        code="PH",
        name=f"pH {suffix}",
        is_enabled=True,
    )
    db.add(sensor)
    await db.flush()
    return device, sensor


async def _sensor_rule(
    db,
    *,
    project: Project,
    sensor: Sensor,
    actor_id: int,
    code: str,
    name: str,
    value: float,
    duration_seconds: int = 0,
    with_project_override: bool = True,
):
    rule = AlertRule(
        code=code,
        name=name,
        target_type="SENSOR",
        evaluator_type="THRESHOLD",
        is_enabled=True,
    )
    db.add(rule)
    await db.flush()
    revision = AlertRuleRevision(
        rule_id=rule.id,
        revision=2,
        business_risk_level="HIGH",
        condition_config={
            "operator": "GT",
            "value": value,
            "duration_seconds": duration_seconds,
        },
        message_template=f"message-{value}",
        consequence=f"consequence-{value}",
        recommended_action=f"action-{value}",
        source_reference="User alert scenario",
        source_order=0,
        status="PUBLISHED",
        created_by=actor_id,
        published_by=actor_id,
    )
    db.add(revision)
    await db.flush()
    rule.current_revision_id = revision.id
    db.add(
        AlertRuleSensorOverride(
            rule_id=rule.id,
            sensor_id=sensor.id,
            config={},
            is_enabled=True,
        )
    )
    if with_project_override:
        db.add(
            AlertRuleProjectOverride(
                rule_id=rule.id,
                project_id=project.id,
                config={},
                is_enabled=True,
            )
        )
    await db.flush()
    return rule


async def _run_backfill(db, *, project, device, catalog):
    connection = await db.connection()

    def invoke(sync_connection):
        _backfill_device(
            sync_connection,
            project_id=project.id,
            device_id=device.id,
            scenario_catalog_id=catalog.id,
            scenario_name=catalog.name,
        )

    await connection.run_sync(invoke)


@pytest.mark.asyncio
async def test_v1_backfill_preserves_edited_runtime_revision_over_catalog() -> None:
    async with AsyncSessionLocal() as db:
        project, admin, catalog, ph_model, ph_item = await _fixture_context(db)
        device, sensor = await _device_with_sensor(
            db, project=project, model=ph_model, suffix=uuid4().hex[:10]
        )
        rule = await _sensor_rule(
            db,
            project=project,
            sensor=sensor,
            actor_id=admin.id,
            code=f"CATALOG_{catalog.id}_{ph_item.id}_PH_HIGH_{uuid4().hex[:8].upper()}",
            name="pH cao mÃ¹a nÃ³ng",
            value=7.2,
            duration_seconds=45,
        )

        await _run_backfill(db, project=project, device=device, catalog=catalog)

        branch = await db.scalar(
            select(ProjectScenarioBranch)
            .join(ProjectScenarioItem)
            .where(
                ProjectScenarioItem.sensor_id == sensor.id,
                ProjectScenarioBranch.branch_key == "PH_HIGH",
            )
        )
        assert branch is not None
        assert branch.name == "pH cao mÃ¹a nÃ³ng"
        assert branch.condition_config["value"] == 7.2
        assert "duration_seconds" not in branch.condition_config
        assert branch.duration_seconds == 45
        item = await db.get(ProjectScenarioItem, branch.project_scenario_item_id)
        assert item is not None
        assert item.source_scenario_catalog_item_id == ph_item.id
        assert await db.get(AlertRule, rule.id) is not None


@pytest.mark.asyncio
async def test_v1_backfill_preserves_unambiguous_manual_runtime_rule() -> None:
    async with AsyncSessionLocal() as db:
        project, admin, catalog, ph_model, _ = await _fixture_context(db)
        device, sensor = await _device_with_sensor(
            db, project=project, model=ph_model, suffix=uuid4().hex[:10]
        )
        manual = await _sensor_rule(
            db,
            project=project,
            sensor=sensor,
            actor_id=admin.id,
            code=f"USER_{uuid4().hex[:16].upper()}",
            name="NgÆ°á»i dÃ¹ng tá»± táº¡o",
            value=8.1,
            with_project_override=False,
        )

        await _run_backfill(db, project=project, device=device, catalog=catalog)

        branch = await db.scalar(
            select(ProjectScenarioBranch)
            .join(ProjectScenarioItem)
            .where(
                ProjectScenarioItem.sensor_id == sensor.id,
                ProjectScenarioBranch.branch_key == f"USER_RULE_{manual.id}",
            )
        )
        assert branch is not None
        assert branch.name == "NgÆ°á»i dÃ¹ng tá»± táº¡o"
        assert branch.condition_config["value"] == 8.1
        assert branch.branch_key == f"USER_RULE_{manual.id}"


@pytest.mark.asyncio
async def test_v1_backfill_rejects_ambiguous_runtime_rule_binding() -> None:
    async with AsyncSessionLocal() as db:
        project, admin, catalog, ph_model, _ = await _fixture_context(db)
        device, first = await _device_with_sensor(
            db, project=project, model=ph_model, suffix=uuid4().hex[:10]
        )
        second = Sensor(
            device_id=device.id,
            sensor_model_id=ph_model.id,
            code="PH-SECOND",
            name="pH second",
            is_enabled=True,
        )
        db.add(second)
        await db.flush()

        rule = await _sensor_rule(
            db,
            project=project,
            sensor=first,
            actor_id=admin.id,
            code=f"USER_AMBIG_{uuid4().hex[:12].upper()}",
            name="Ambiguous",
            value=7.9,
            with_project_override=False,
        )
        db.add(
            AlertRuleSensorOverride(
                rule_id=rule.id,
                sensor_id=second.id,
                config={},
                is_enabled=True,
            )
        )
        await db.flush()

        with pytest.raises(
            RuntimeError,
            match=rf"V1_SCENARIO_SYNC_AMBIGUOUS_RULE:{rule.id}",
        ):
            await _run_backfill(db, project=project, device=device, catalog=catalog)


@pytest.mark.asyncio
async def test_v1_backfill_creates_one_active_scenario_with_all_device_resources() -> None:
    async with AsyncSessionLocal() as db:
        project, _, catalog, ph_model, _ = await _fixture_context(db)
        device, sensor = await _device_with_sensor(
            db, project=project, model=ph_model, suffix=uuid4().hex[:10]
        )

        await _run_backfill(db, project=project, device=device, catalog=catalog)

        scenario = await db.scalar(
            select(ProjectScenario).where(ProjectScenario.device_id == device.id)
        )
        assert scenario is not None
        assert scenario.is_active is True
        assert scenario.source_scenario_catalog_id == catalog.id
        item = await db.scalar(
            select(ProjectScenarioItem).where(
                ProjectScenarioItem.project_scenario_id == scenario.id,
                ProjectScenarioItem.sensor_id == sensor.id,
            )
        )
        assert item is not None


@pytest.mark.asyncio
async def test_v1_schema_sync_is_idempotent_and_keeps_revision_v1() -> None:
    async with AsyncSessionLocal() as db:
        connection = await db.connection()

        await connection.run_sync(_ensure_v1_project_scenario_schema)
        await connection.run_sync(_ensure_v1_project_scenario_schema)

        version = await db.scalar(text("SELECT version_num FROM alembic_version"))
        assert version == "v1"
