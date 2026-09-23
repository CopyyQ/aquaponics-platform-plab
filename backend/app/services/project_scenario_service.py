from __future__ import annotations

import copy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ApplicationError, ErrorDetail
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.sensor import Sensor
from app.models.user import User
from app.schemas.project_scenario import (
    ProjectScenarioActivationRead,
    ProjectScenarioBranchCreate,
    ProjectScenarioBranchRead,
    ProjectScenarioBranchUpdate,
    ProjectScenarioCreate,
    ProjectScenarioDetailRead,
    ProjectScenarioItemRead,
    ProjectScenarioItemUpdate,
    ProjectScenarioMetadataUpdate,
    ProjectScenarioResourceRead,
    ProjectScenarioSummaryRead,
)
from app.services.alert_evaluators import validate_condition_config


def _scenario_loader():
    return selectinload(ProjectScenario.items).options(
        selectinload(ProjectScenarioItem.sensor),
        selectinload(ProjectScenarioItem.actuator),
        selectinload(ProjectScenarioItem.branches),
    )


async def list_project_scenarios(
    db: AsyncSession,
    *,
    device: Device,
) -> list[ProjectScenario]:
    return list(
        (
            await db.scalars(
                select(ProjectScenario)
                .where(
                    ProjectScenario.device_id == device.id,
                    ProjectScenario.retired_at.is_(None),
                )
                .options(_scenario_loader(), selectinload(ProjectScenario.cloned_from_scenario))
                .order_by(
                    ProjectScenario.is_active.desc(),
                    ProjectScenario.created_at.asc(),
                    ProjectScenario.id.asc(),
                )
            )
        )
        .unique()
        .all()
    )


async def get_project_scenario(
    db: AsyncSession,
    *,
    device: Device,
    public_id: UUID,
) -> ProjectScenario:
    scenario = await db.scalar(
        select(ProjectScenario)
        .where(
            ProjectScenario.device_id == device.id,
            ProjectScenario.public_id == public_id,
            ProjectScenario.retired_at.is_(None),
        )
        .options(_scenario_loader(), selectinload(ProjectScenario.cloned_from_scenario))
    )
    if scenario is None:
        raise ApplicationError(
            "PROJECT_SCENARIO_NOT_FOUND",
            "Không tìm thấy kịch bản của thiết bị",
            404,
        )
    return scenario


async def _active_resources(
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


async def create_project_scenario(
    db: AsyncSession,
    *,
    device: Device,
    actor_id: int,
    payload: ProjectScenarioCreate,
) -> ProjectScenario:
    if payload.clone_from_scenario_id is not None:
        source = await get_project_scenario(
            db,
            device=device,
            public_id=payload.clone_from_scenario_id,
        )
        return await clone_project_scenario(
            db,
            source=source,
            actor_id=actor_id,
            name=payload.name,
            description=payload.description,
        )

    scenario = ProjectScenario(
        project_id=device.project_id,
        device_id=device.id,
        name=payload.name.strip(),
        description=payload.description,
        is_active=False,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(scenario)
    await db.flush()

    sensors, actuators = await _active_resources(db, device=device)
    items: list[ProjectScenarioItem] = []
    for sensor in sensors:
        items.append(
            ProjectScenarioItem(
                scenario=scenario,
                target_type="SENSOR",
                sensor_id=sensor.id,
                actuator_id=None,
                name=sensor.name,
                is_enabled=True,
            )
        )
    for actuator in actuators:
        items.append(
            ProjectScenarioItem(
                scenario=scenario,
                target_type="ACTUATOR",
                sensor_id=None,
                actuator_id=actuator.id,
                name=actuator.name,
                is_enabled=True,
            )
        )
    db.add_all(items)
    await db.flush()
    return await _reload_scenario(db, scenario.id)


async def _reload_scenario(
    db: AsyncSession,
    scenario_id: int,
) -> ProjectScenario:
    scenario = await db.scalar(
        select(ProjectScenario)
        .where(ProjectScenario.id == scenario_id)
        .options(_scenario_loader(), selectinload(ProjectScenario.cloned_from_scenario))
    )
    if scenario is None:
        raise ApplicationError(
            "PROJECT_SCENARIO_NOT_FOUND",
            "Không tìm thấy kịch bản của thiết bị",
            404,
        )
    return scenario


async def clone_project_scenario(
    db: AsyncSession,
    *,
    source: ProjectScenario,
    actor_id: int,
    name: str,
    description: str | None,
) -> ProjectScenario:
    source = await _reload_scenario(db, source.id)
    clone = ProjectScenario(
        project_id=source.project_id,
        device_id=source.device_id,
        name=name.strip(),
        description=description,
        is_active=False,
        source_scenario_catalog_id=source.source_scenario_catalog_id,
        cloned_from_scenario_id=source.id,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(clone)
    await db.flush()

    for source_item in source.items:
        if source_item.retired_at is not None:
            continue
        cloned_item = ProjectScenarioItem(
            scenario=clone,
            target_type=source_item.target_type,
            sensor_id=source_item.sensor_id,
            actuator_id=source_item.actuator_id,
            name=source_item.name,
            is_enabled=source_item.is_enabled,
            source_scenario_catalog_item_id=source_item.source_scenario_catalog_item_id,
            notes=source_item.notes,
        )
        db.add(cloned_item)
        await db.flush()
        for source_branch in source_item.branches:
            if source_branch.retired_at is not None:
                continue
            db.add(
                ProjectScenarioBranch(
                    item=cloned_item,
                    branch_key=source_branch.branch_key,
                    name=source_branch.name,
                    evaluator_type=source_branch.evaluator_type,
                    condition_config=copy.deepcopy(source_branch.condition_config),
                    duration_seconds=source_branch.duration_seconds,
                    business_risk_level=source_branch.business_risk_level,
                    message_template=source_branch.message_template,
                    consequence=source_branch.consequence,
                    recommended_action=source_branch.recommended_action,
                    is_enabled=source_branch.is_enabled,
                    position=source_branch.position,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
    await db.flush()
    return await _reload_scenario(db, clone.id)


async def update_project_scenario_metadata(
    db: AsyncSession,
    *,
    scenario: ProjectScenario,
    actor_id: int,
    payload: ProjectScenarioMetadataUpdate,
) -> ProjectScenario:
    if payload.name is not None:
        scenario.name = payload.name.strip()
    if "description" in payload.model_fields_set:
        scenario.description = payload.description
    scenario.updated_by = actor_id
    await db.flush()
    await db.refresh(scenario, attribute_names=["updated_at"])
    return scenario


async def retire_project_scenario(
    db: AsyncSession,
    *,
    scenario: ProjectScenario,
    actor_id: int,
    retired_at: datetime,
) -> None:
    if scenario.is_active:
        raise ApplicationError(
            "ACTIVE_SCENARIO_CANNOT_BE_DELETED",
            "Không thể xóa kịch bản đang được sử dụng",
            409,
        )
    scenario.is_active = False
    scenario.retired_at = retired_at
    scenario.updated_by = actor_id
    await db.flush()


async def get_project_scenario_item(
    db: AsyncSession,
    *,
    scenario: ProjectScenario,
    public_id: UUID,
) -> ProjectScenarioItem:
    item = await db.scalar(
        select(ProjectScenarioItem)
        .where(
            ProjectScenarioItem.project_scenario_id == scenario.id,
            ProjectScenarioItem.public_id == public_id,
            ProjectScenarioItem.retired_at.is_(None),
        )
        .options(
            selectinload(ProjectScenarioItem.sensor),
            selectinload(ProjectScenarioItem.actuator),
            selectinload(ProjectScenarioItem.branches),
        )
    )
    if item is None:
        raise ApplicationError(
            "PROJECT_SCENARIO_ITEM_NOT_FOUND",
            "Không tìm thấy tài nguyên trong kịch bản",
            404,
        )
    return item


async def update_project_scenario_item(
    db: AsyncSession,
    *,
    item: ProjectScenarioItem,
    actor_id: int,
    payload: ProjectScenarioItemUpdate,
) -> ProjectScenarioItem:
    values = payload.model_dump(exclude_unset=True)
    for field, value in values.items():
        if field == "name" and value is not None:
            value = value.strip()
        setattr(item, field, value)
    await db.flush()
    return item


async def get_project_scenario_branch(
    db: AsyncSession,
    *,
    item: ProjectScenarioItem,
    public_id: UUID,
) -> ProjectScenarioBranch:
    branch = await db.scalar(
        select(ProjectScenarioBranch).where(
            ProjectScenarioBranch.project_scenario_item_id == item.id,
            ProjectScenarioBranch.public_id == public_id,
            ProjectScenarioBranch.retired_at.is_(None),
        )
    )
    if branch is None:
        raise ApplicationError(
            "PROJECT_SCENARIO_BRANCH_NOT_FOUND",
            "Không tìm thấy nhánh kịch bản",
            404,
        )
    return branch


async def activate_project_scenario(
    db: AsyncSession,
    *,
    device: Device,
    target: ProjectScenario,
    actor: User,
    activated_at: datetime,
) -> ProjectScenarioActivationRead:
    from app.services.project_scenario_evaluator import (
        reevaluate_active_scenario_resources,
        resolve_scenario_incidents,
    )

    if target.device_id != device.id or target.retired_at is not None:
        raise ApplicationError(
            "SCENARIO_DOES_NOT_BELONG_TO_DEVICE",
            "Kịch bản không thuộc thiết bị này",
            404,
        )

    lock_acquired = bool(
        await db.scalar(select(func.pg_try_advisory_xact_lock(device.id)))
    )
    if not lock_acquired:
        raise ApplicationError(
            "SCENARIO_ACTIVATION_CONFLICT",
            "Thiết bị đang được chuyển kịch bản bởi một thao tác khác",
            409,
        )

    locked_device = await db.scalar(
        select(Device)
        .where(Device.id == device.id, Device.is_deleted.is_(False))
        .with_for_update()
    )
    if locked_device is None:
        raise ApplicationError("DEVICE_NOT_FOUND", "Không tìm thấy thiết bị", 404)

    locked_target = await db.scalar(
        select(ProjectScenario)
        .where(
            ProjectScenario.id == target.id,
            ProjectScenario.device_id == device.id,
            ProjectScenario.retired_at.is_(None),
        )
        .options(
            _scenario_loader(),
            selectinload(ProjectScenario.cloned_from_scenario),
        )
        .with_for_update()
    )
    if locked_target is None:
        raise ApplicationError(
            "PROJECT_SCENARIO_NOT_FOUND",
            "Không tìm thấy kịch bản của thiết bị",
            404,
        )

    current = await db.scalar(
        select(ProjectScenario)
        .where(
            ProjectScenario.device_id == device.id,
            ProjectScenario.is_active.is_(True),
            ProjectScenario.retired_at.is_(None),
        )
        .with_for_update()
    )
    previous_public_id = current.public_id if current is not None else None

    if current is not None and current.id == locked_target.id:
        return ProjectScenarioActivationRead(
            scenario=scenario_summary_read(locked_target),
            previous_scenario_id=previous_public_id,
        )

    closed_incident_count = 0
    try:
        if current is not None:
            closed_incident_count = await resolve_scenario_incidents(
                db,
                scenario_id=current.id,
                reason="SCENARIO_CHANGED",
                resolved_at=activated_at,
                enqueue_recovery=False,
            )
            current.is_active = False
            current.updated_by = actor.id
            await db.flush()

        locked_target.is_active = True
        locked_target.updated_by = actor.id
        await db.flush()
        await db.refresh(locked_target, attribute_names=["updated_at"])
    except IntegrityError as exc:
        await db.rollback()
        raise ApplicationError(
            "SCENARIO_ACTIVATION_CONFLICT",
            "Không thể chuyển kịch bản do xung đột đồng thời",
            409,
        ) from exc

    reevaluated_sensor_count, reevaluated_actuator_count = (
        await reevaluate_active_scenario_resources(
            db,
            scenario=locked_target,
            observed_at=activated_at,
        )
    )
    return ProjectScenarioActivationRead(
        scenario=scenario_summary_read(locked_target),
        previous_scenario_id=previous_public_id,
        closed_incident_count=closed_incident_count,
        reevaluated_sensor_count=reevaluated_sensor_count,
        reevaluated_actuator_count=reevaluated_actuator_count,
    )


def _branch_validation_errors(
    *,
    evaluator_type: str,
    condition_config: dict,
) -> tuple[ErrorDetail, ...]:
    errors = validate_condition_config(evaluator_type, condition_config)
    return tuple(
        ErrorDetail(
            field="condition_config",
            message=f"Thiếu hoặc sai cấu hình: {field}",
            type="value_error",
        )
        for field in errors
    )


async def create_project_scenario_branch(
    db: AsyncSession,
    *,
    item: ProjectScenarioItem,
    actor_id: int,
    payload: ProjectScenarioBranchCreate,
) -> ProjectScenarioBranch:
    errors = _branch_validation_errors(
        evaluator_type=payload.evaluator_type,
        condition_config=payload.condition_config,
    )
    if errors:
        raise ApplicationError(
            "SCENARIO_BRANCH_INVALID",
            "Cấu hình điều kiện kịch bản không hợp lệ",
            422,
            errors,
        )

    branch = ProjectScenarioBranch(
        item=item,
        branch_key=payload.branch_key or f"USER_{uuid4().hex[:16].upper()}",
        name=payload.name.strip(),
        evaluator_type=payload.evaluator_type,
        condition_config=copy.deepcopy(payload.condition_config),
        duration_seconds=payload.duration_seconds,
        business_risk_level=payload.business_risk_level,
        message_template=payload.message_template,
        consequence=payload.consequence,
        recommended_action=payload.recommended_action,
        is_enabled=payload.is_enabled,
        position=payload.position,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(branch)
    await db.flush()
    return branch


async def update_project_scenario_branch(
    db: AsyncSession,
    *,
    branch: ProjectScenarioBranch,
    actor_id: int,
    payload: ProjectScenarioBranchUpdate,
) -> ProjectScenarioBranch:
    evaluator_type = payload.evaluator_type or branch.evaluator_type
    condition_config = (
        payload.condition_config
        if payload.condition_config is not None
        else branch.condition_config
    )
    errors = _branch_validation_errors(
        evaluator_type=evaluator_type,
        condition_config=condition_config,
    )
    if errors:
        raise ApplicationError(
            "SCENARIO_BRANCH_INVALID",
            "Cấu hình điều kiện kịch bản không hợp lệ",
            422,
            errors,
        )

    before_evaluator_type = branch.evaluator_type
    before_condition = copy.deepcopy(branch.condition_config)
    before_duration_seconds = branch.duration_seconds
    before_is_enabled = branch.is_enabled

    values = payload.model_dump(exclude_unset=True)
    for field, value in values.items():
        if field == "condition_config" and value is not None:
            value = copy.deepcopy(value)
        setattr(branch, field, value)
    branch.updated_by = actor_id
    await db.flush()
    await db.refresh(branch, attribute_names=["updated_at"])

    semantic_changed = (
        branch.evaluator_type != before_evaluator_type
        or branch.condition_config != before_condition
        or branch.duration_seconds != before_duration_seconds
        or branch.is_enabled != before_is_enabled
    )
    if semantic_changed:
        from app.services.project_scenario_evaluator import reconcile_changed_branch

        await reconcile_changed_branch(
            db,
            branch=branch,
            before_condition=before_condition,
            before_evaluator_type=before_evaluator_type,
            before_duration_seconds=before_duration_seconds,
            changed_at=datetime.now(UTC),
        )
    return branch


async def retire_project_scenario_branch(
    db: AsyncSession,
    *,
    branch: ProjectScenarioBranch,
    actor_id: int,
    retired_at: datetime,
) -> None:
    branch.is_enabled = False
    branch.retired_at = retired_at
    branch.updated_by = actor_id
    await db.flush()


def project_scenario_branch_read(branch: ProjectScenarioBranch) -> ProjectScenarioBranchRead:
    return ProjectScenarioBranchRead(
        id=branch.public_id,
        branch_key=branch.branch_key,
        name=branch.name,
        evaluator_type=branch.evaluator_type,
        condition_config=copy.deepcopy(branch.condition_config),
        duration_seconds=branch.duration_seconds,
        business_risk_level=branch.business_risk_level,
        message_template=branch.message_template,
        consequence=branch.consequence,
        recommended_action=branch.recommended_action,
        is_enabled=branch.is_enabled,
        position=branch.position,
        created_at=branch.created_at,
        updated_at=branch.updated_at,
    )


def project_scenario_item_read(item: ProjectScenarioItem) -> ProjectScenarioItemRead:
    if item.target_type == "SENSOR":
        resource = item.sensor
        if resource is None:
            raise ApplicationError(
                "SCENARIO_RESOURCE_MISMATCH",
                "Kịch bản cảm biến không còn resource tương ứng",
                409,
            )
        resource_read = ProjectScenarioResourceRead(
            id=resource.public_id,
            code=resource.code,
            name=resource.name,
            model_id=resource.sensor_model_id,
            is_enabled=resource.is_enabled,
        )
    else:
        resource = item.actuator
        if resource is None:
            raise ApplicationError(
                "SCENARIO_RESOURCE_MISMATCH",
                "Kịch bản cơ cấu chấp hành không còn resource tương ứng",
                409,
            )
        resource_read = ProjectScenarioResourceRead(
            id=resource.public_id,
            code=resource.code,
            name=resource.name,
            model_id=resource.actuator_model_id,
            is_enabled=resource.is_enabled,
        )

    return ProjectScenarioItemRead(
        id=item.public_id,
        target_type=item.target_type,
        resource=resource_read,
        name=item.name,
        is_enabled=item.is_enabled,
        branches=[
            project_scenario_branch_read(branch)
            for branch in item.branches
            if branch.retired_at is None
        ],
    )


def scenario_summary_read(
    scenario: ProjectScenario,
) -> ProjectScenarioSummaryRead:
    active_items = [item for item in scenario.items if item.retired_at is None]
    cloned_from_public_id = (
        scenario.cloned_from_scenario.public_id
        if scenario.cloned_from_scenario is not None
        else None
    )
    return ProjectScenarioSummaryRead(
        id=scenario.public_id,
        name=scenario.name,
        description=scenario.description,
        is_active=scenario.is_active,
        sensor_count=sum(item.target_type == "SENSOR" for item in active_items),
        actuator_count=sum(item.target_type == "ACTUATOR" for item in active_items),
        source_scenario_catalog_id=scenario.source_scenario_catalog_id,
        cloned_from_scenario_id=cloned_from_public_id,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


def scenario_detail_read(
    scenario: ProjectScenario,
) -> ProjectScenarioDetailRead:
    summary = scenario_summary_read(scenario)
    items = [item for item in scenario.items if item.retired_at is None]
    return ProjectScenarioDetailRead(
        **summary.model_dump(),
        sensors=[
            project_scenario_item_read(item)
            for item in items
            if item.target_type == "SENSOR"
        ],
        actuators=[
            project_scenario_item_read(item)
            for item in items
            if item.target_type == "ACTUATOR"
        ],
    )
