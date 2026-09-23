from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.device_template import DeviceTemplate, DeviceTemplateActuator, DeviceTemplateSensor
from app.models.scenario_catalog import ScenarioCatalog, ScenarioCatalogItem
from app.schemas.scenario_catalog import (
    ScenarioCatalogCreate,
    ScenarioCatalogItemUpdate,
    ScenarioCatalogUpdate,
)
from app.services.alert_evaluators import validate_condition_config


class ScenarioCatalogError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _options():
    return (
        selectinload(ScenarioCatalog.items).selectinload(ScenarioCatalogItem.sensor_model),
        selectinload(ScenarioCatalog.items).selectinload(ScenarioCatalogItem.actuator_model),
    )


async def get_scenario_catalog(
    db: AsyncSession,
    catalog_id: int,
    *,
    active_only: bool = False,
    device_template_id: int | None = None,
) -> ScenarioCatalog:
    query = (
        select(ScenarioCatalog)
        .options(*_options())
        .where(
            ScenarioCatalog.id == catalog_id,
            ScenarioCatalog.is_deleted.is_(False),
        )
    )
    if active_only:
        query = query.where(ScenarioCatalog.is_active.is_(True))
    if device_template_id is not None:
        query = query.where(ScenarioCatalog.device_template_id == device_template_id)
    row = await db.scalar(query)
    if row is None:
        raise ScenarioCatalogError("SCENARIO_CATALOG_NOT_FOUND", "Không tìm thấy kịch bản của thiết bị", 404)
    return row


async def list_scenario_catalogs(
    db: AsyncSession, *, device_template_id: int | None = None
) -> list[ScenarioCatalog]:
    query = (
        select(ScenarioCatalog)
        .options(*_options())
        .where(ScenarioCatalog.is_deleted.is_(False))
    )
    if device_template_id is not None:
        query = query.where(ScenarioCatalog.device_template_id == device_template_id)
    return list(
        (
            await db.scalars(query.order_by(ScenarioCatalog.name))
        )
        .unique()
        .all()
    )


async def _scenario_device_template(
    db: AsyncSession, device_template_id: int
) -> DeviceTemplate:
    row = await db.scalar(
        select(DeviceTemplate)
        .options(
            selectinload(DeviceTemplate.sensor_mappings).selectinload(
                DeviceTemplateSensor.sensor_model
            ),
            selectinload(DeviceTemplate.actuator_mappings).selectinload(
                DeviceTemplateActuator.actuator_model
            ),
        )
        .where(
            DeviceTemplate.id == device_template_id,
            DeviceTemplate.is_deleted.is_(False),
            DeviceTemplate.is_active.is_(True),
        )
    )
    if row is None:
        raise ScenarioCatalogError(
            "DEVICE_TEMPLATE_NOT_AVAILABLE",
            "Thiết bị không tồn tại hoặc không hoạt động",
            422,
        )
    return row


async def sync_catalog_items(db: AsyncSession, catalog: ScenarioCatalog) -> None:
    template = await _scenario_device_template(db, catalog.device_template_id)
    desired_sensors = {
        mapping.code: (
            mapping.sensor_model_id,
            mapping.display_name or mapping.sensor_model.name,
        )
        for mapping in template.sensor_mappings
    }
    desired_actuators = {
        mapping.code: (
            mapping.actuator_model_id,
            mapping.default_name or mapping.actuator_model.name,
        )
        for mapping in template.actuator_mappings
    }
    existing = list(
        (
            await db.scalars(
                select(ScenarioCatalogItem).where(
                    ScenarioCatalogItem.scenario_catalog_id == catalog.id
                )
            )
        ).all()
    )
    existing_sensors = {
        item.resource_code: item
        for item in existing
        if item.target_type == "SENSOR"
    }
    existing_actuators = {
        item.resource_code: item
        for item in existing
        if item.target_type == "ACTUATOR"
    }

    for resource_code, item in existing_sensors.items():
        desired = desired_sensors.get(resource_code)
        if desired is None:
            await db.delete(item)
        else:
            item.sensor_model_id, item.name = desired
    for resource_code, item in existing_actuators.items():
        desired = desired_actuators.get(resource_code)
        if desired is None:
            await db.delete(item)
        else:
            item.actuator_model_id, item.name = desired

    for resource_code, (model_id, name) in desired_sensors.items():
        if resource_code not in existing_sensors:
            db.add(
                ScenarioCatalogItem(
                    scenario_catalog_id=catalog.id,
                    target_type="SENSOR",
                    resource_code=resource_code,
                    sensor_model_id=model_id,
                    name=name,
                    is_enabled=False,
                    branches=[],
                )
            )
    for resource_code, (model_id, name) in desired_actuators.items():
        if resource_code not in existing_actuators:
            db.add(
                ScenarioCatalogItem(
                    scenario_catalog_id=catalog.id,
                    target_type="ACTUATOR",
                    resource_code=resource_code,
                    actuator_model_id=model_id,
                    name=name,
                    is_enabled=False,
                    branches=[],
                )
            )
    await db.flush()


async def populate_catalog_items(db: AsyncSession, catalog: ScenarioCatalog) -> None:
    await sync_catalog_items(db, catalog)


async def sync_scenario_catalogs_for_template(
    db: AsyncSession, device_template_id: int
) -> None:
    catalogs = await list_scenario_catalogs(db, device_template_id=device_template_id)
    for catalog in catalogs:
        await sync_catalog_items(db, catalog)


async def create_scenario_catalog(
    db: AsyncSession, payload: ScenarioCatalogCreate
) -> ScenarioCatalog:
    if await db.scalar(
        select(ScenarioCatalog.id).where(ScenarioCatalog.code == payload.code)
    ):
        raise ScenarioCatalogError(
            "SCENARIO_CATALOG_CODE_EXISTS", "Mã kịch bản đã tồn tại", 409
        )
    await _scenario_device_template(db, payload.device_template_id)
    row = ScenarioCatalog(**payload.model_dump(), is_active=True)
    db.add(row)
    await db.flush()
    await populate_catalog_items(db, row)
    await db.commit()
    return await get_scenario_catalog(db, row.id)


async def update_scenario_catalog(
    db: AsyncSession, catalog_id: int, payload: ScenarioCatalogUpdate
) -> ScenarioCatalog:
    row = await get_scenario_catalog(db, catalog_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    return await get_scenario_catalog(db, catalog_id)


async def delete_scenario_catalog(db: AsyncSession, catalog_id: int) -> None:
    row = await get_scenario_catalog(db, catalog_id)
    row.is_deleted = True
    row.deleted_at = datetime.now(UTC)
    row.is_active = False
    await db.commit()


async def update_scenario_catalog_item(
    db: AsyncSession,
    catalog_id: int,
    item_id: int,
    payload: ScenarioCatalogItemUpdate,
) -> ScenarioCatalogItem:
    await get_scenario_catalog(db, catalog_id)
    row = await db.scalar(
        select(ScenarioCatalogItem)
        .options(
            selectinload(ScenarioCatalogItem.sensor_model),
            selectinload(ScenarioCatalogItem.actuator_model),
        )
        .where(
            ScenarioCatalogItem.id == item_id,
            ScenarioCatalogItem.scenario_catalog_id == catalog_id,
        )
    )
    if row is None:
        raise ScenarioCatalogError("SCENARIO_ITEM_NOT_FOUND", "Không tìm thấy mục kịch bản", 404)

    values = payload.model_dump(exclude_unset=True)
    if "branches" in values and values["branches"] is not None:
        branches = values["branches"]
        for branch in branches:
            if not branch.get("enabled", True):
                continue
            errors = validate_condition_config(
                branch["evaluator_type"], branch["condition_config"]
            )
            if errors:
                raise ScenarioCatalogError(
                    "INVALID_SCENARIO_BRANCH",
                    f"Nhánh {branch['key']} chưa hợp lệ: {', '.join(errors)}",
                )
        values["branches"] = branches
    for field, value in values.items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row
