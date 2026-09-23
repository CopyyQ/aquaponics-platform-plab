from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ApplicationError
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.scenario_catalog import ScenarioCatalog, ScenarioCatalogItem
from app.models.sensor import Sensor
from app.services.alert_evaluators import validate_condition_config


def _matching_catalog_item(
    catalog: ScenarioCatalog,
    *,
    target_type: str,
    resource: Sensor | Actuator,
) -> ScenarioCatalogItem | None:
    if target_type == "SENSOR":
        model_id = resource.sensor_model_id
        candidates = [
            item
            for item in catalog.items
            if item.target_type == "SENSOR"
            and item.sensor_model_id == model_id
        ]
    else:
        model_id = resource.actuator_model_id
        candidates = [
            item
            for item in catalog.items
            if item.target_type == "ACTUATOR"
            and item.actuator_model_id == model_id
        ]

    exact = [item for item in candidates if item.resource_code == resource.code]
    if len(exact) == 1:
        return exact[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _branch_duration(branch: dict[str, Any]) -> int:
    if branch.get("duration_seconds") is not None:
        return int(branch["duration_seconds"])
    config = branch.get("condition_config")
    if isinstance(config, dict) and config.get("duration_seconds") is not None:
        return int(config["duration_seconds"])
    return 0


def _new_item(
    *,
    scenario: ProjectScenario,
    target_type: str,
    resource: Sensor | Actuator,
    catalog_item: ScenarioCatalogItem | None,
) -> ProjectScenarioItem:
    return ProjectScenarioItem(
        scenario=scenario,
        target_type=target_type,
        sensor_id=resource.id if target_type == "SENSOR" else None,
        actuator_id=resource.id if target_type == "ACTUATOR" else None,
        name=resource.name,
        is_enabled=(
            bool(catalog_item.is_enabled)
            if catalog_item is not None
            else bool(resource.is_enabled)
        ),
        source_scenario_catalog_item_id=(
            catalog_item.id if catalog_item is not None else None
        ),
    )


async def _copy_catalog_branches(
    db: AsyncSession,
    *,
    item: ProjectScenarioItem,
    catalog_item: ScenarioCatalogItem | None,
    actor_id: int,
) -> None:
    if catalog_item is None or not catalog_item.is_enabled:
        return

    for position, source in enumerate(catalog_item.branches or []):
        if not source.get("enabled", True):
            continue
        evaluator_type = str(source["evaluator_type"])
        condition_config = copy.deepcopy(source["condition_config"])
        errors = validate_condition_config(evaluator_type, condition_config)
        if errors:
            raise ApplicationError(
                "INVALID_SCENARIO_BRANCH",
                (
                    f"Nhánh {source.get('key')} chưa hợp lệ: "
                    f"{', '.join(errors)}"
                ),
                422,
            )

        db.add(
            ProjectScenarioBranch(
                item=item,
                branch_key=str(source["key"]),
                name=str(source.get("label") or source["key"]),
                evaluator_type=evaluator_type,
                condition_config=condition_config,
                duration_seconds=_branch_duration(source),
                business_risk_level=str(source.get("risk_level") or "MEDIUM"),
                message_template=source.get("message"),
                consequence=source.get("consequence"),
                recommended_action=source.get("recommended_action"),
                is_enabled=True,
                position=position,
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
    await db.flush()


async def _catalog_with_items(
    db: AsyncSession,
    catalog_id: int,
) -> ScenarioCatalog | None:
    return await db.scalar(
        select(ScenarioCatalog)
        .options(selectinload(ScenarioCatalog.items))
        .where(
            ScenarioCatalog.id == catalog_id,
            ScenarioCatalog.is_deleted.is_(False),
        )
    )


async def _active_device_resources(
    db: AsyncSession,
    *,
    device: Device,
) -> tuple[list[Sensor], list[Actuator]]:
    sensors = list(
        (
            await db.scalars(
                select(Sensor)
                .where(
                    Sensor.device_id == device.id,
                    Sensor.is_deleted.is_(False),
                )
                .order_by(Sensor.id)
            )
        ).all()
    )
    actuators = list(
        (
            await db.scalars(
                select(Actuator)
                .where(
                    Actuator.device_id == device.id,
                    Actuator.is_deleted.is_(False),
                )
                .order_by(Actuator.id)
            )
        ).all()
    )
    return sensors, actuators


async def clone_catalog_to_project_scenario(
    db: AsyncSession,
    *,
    catalog: ScenarioCatalog,
    device: Device,
    actor_id: int,
    name: str | None = None,
) -> ProjectScenario:
    existing_scenario_id = await db.scalar(
        select(ProjectScenario.id)
        .where(
            ProjectScenario.device_id == device.id,
            ProjectScenario.retired_at.is_(None),
        )
        .limit(1)
    )
    scenario = ProjectScenario(
        project_id=device.project_id,
        device_id=device.id,
        name=(name or catalog.name).strip(),
        description=catalog.description,
        is_active=existing_scenario_id is None,
        source_scenario_catalog_id=catalog.id,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(scenario)
    await db.flush()

    sensors, actuators = await _active_device_resources(db, device=device)
    for sensor in sensors:
        catalog_item = _matching_catalog_item(
            catalog,
            target_type="SENSOR",
            resource=sensor,
        )
        item = _new_item(
            scenario=scenario,
            target_type="SENSOR",
            resource=sensor,
            catalog_item=catalog_item,
        )
        db.add(item)
        await db.flush()
        await _copy_catalog_branches(
            db,
            item=item,
            catalog_item=catalog_item,
            actor_id=actor_id,
        )

    for actuator in actuators:
        catalog_item = _matching_catalog_item(
            catalog,
            target_type="ACTUATOR",
            resource=actuator,
        )
        item = _new_item(
            scenario=scenario,
            target_type="ACTUATOR",
            resource=actuator,
            catalog_item=catalog_item,
        )
        db.add(item)
        await db.flush()
        await _copy_catalog_branches(
            db,
            item=item,
            catalog_item=catalog_item,
            actor_id=actor_id,
        )

    await db.flush()
    await db.refresh(
        scenario,
        attribute_names=["items", "updated_at"],
    )
    for item in scenario.items:
        await db.refresh(
            item,
            attribute_names=["sensor", "actuator", "branches"],
        )
    return scenario


async def _sync_resource_to_scenarios(
    db: AsyncSession,
    *,
    device: Device,
    target_type: str,
    resource: Sensor | Actuator,
    actor_id: int,
) -> int:
    scenarios = list(
        (
            await db.scalars(
                select(ProjectScenario)
                .where(
                    ProjectScenario.device_id == device.id,
                    ProjectScenario.retired_at.is_(None),
                )
                .order_by(ProjectScenario.id)
            )
        ).all()
    )
    created = 0
    catalog_cache: dict[int, ScenarioCatalog | None] = {}

    for scenario in scenarios:
        existing = await db.scalar(
            select(ProjectScenarioItem.id).where(
                ProjectScenarioItem.project_scenario_id == scenario.id,
                ProjectScenarioItem.retired_at.is_(None),
                (
                    ProjectScenarioItem.sensor_id == resource.id
                    if target_type == "SENSOR"
                    else ProjectScenarioItem.actuator_id == resource.id
                ),
            )
        )
        if existing is not None:
            continue

        catalog_item = None
        if scenario.source_scenario_catalog_id is not None:
            catalog_id = scenario.source_scenario_catalog_id
            if catalog_id not in catalog_cache:
                catalog_cache[catalog_id] = await _catalog_with_items(
                    db, catalog_id
                )
            catalog = catalog_cache[catalog_id]
            if catalog is not None:
                catalog_item = _matching_catalog_item(
                    catalog,
                    target_type=target_type,
                    resource=resource,
                )

        item = _new_item(
            scenario=scenario,
            target_type=target_type,
            resource=resource,
            catalog_item=catalog_item,
        )
        db.add(item)
        await db.flush()
        await _copy_catalog_branches(
            db,
            item=item,
            catalog_item=catalog_item,
            actor_id=actor_id,
        )
        created += 1

    await db.flush()
    return created


async def sync_new_sensor_to_scenarios(
    db: AsyncSession,
    *,
    device: Device,
    sensor: Sensor,
    actor_id: int,
) -> int:
    return await _sync_resource_to_scenarios(
        db,
        device=device,
        target_type="SENSOR",
        resource=sensor,
        actor_id=actor_id,
    )


async def sync_new_actuator_to_scenarios(
    db: AsyncSession,
    *,
    device: Device,
    actuator: Actuator,
    actor_id: int,
) -> int:
    return await _sync_resource_to_scenarios(
        db,
        device=device,
        target_type="ACTUATOR",
        resource=actuator,
        actor_id=actor_id,
    )


async def _retire_resource_from_scenarios(
    db: AsyncSession,
    *,
    device: Device,
    target_type: str,
    resource_id: int,
    actor_id: int,
    retired_at: datetime,
) -> int:
    query = (
        select(ProjectScenarioItem)
        .options(selectinload(ProjectScenarioItem.branches))
        .join(
            ProjectScenario,
            ProjectScenario.id == ProjectScenarioItem.project_scenario_id,
        )
        .where(
            ProjectScenario.device_id == device.id,
            ProjectScenario.retired_at.is_(None),
            ProjectScenarioItem.retired_at.is_(None),
            ProjectScenarioItem.target_type == target_type,
        )
    )
    query = query.where(
        ProjectScenarioItem.sensor_id == resource_id
        if target_type == "SENSOR"
        else ProjectScenarioItem.actuator_id == resource_id
    )
    items = list((await db.scalars(query)).unique().all())
    for item in items:
        item.is_enabled = False
        item.retired_at = retired_at
        for branch in item.branches:
            if branch.retired_at is None:
                branch.is_enabled = False
                branch.retired_at = retired_at
                branch.updated_by = actor_id
    await db.flush()
    return len(items)


async def retire_sensor_from_scenarios(
    db: AsyncSession,
    *,
    device: Device,
    sensor: Sensor,
    actor_id: int,
    retired_at: datetime,
) -> int:
    return await _retire_resource_from_scenarios(
        db,
        device=device,
        target_type="SENSOR",
        resource_id=sensor.id,
        actor_id=actor_id,
        retired_at=retired_at,
    )


async def retire_actuator_from_scenarios(
    db: AsyncSession,
    *,
    device: Device,
    actuator: Actuator,
    actor_id: int,
    retired_at: datetime,
) -> int:
    return await _retire_resource_from_scenarios(
        db,
        device=device,
        target_type="ACTUATOR",
        resource_id=actuator.id,
        actor_id=actor_id,
        retired_at=retired_at,
    )
