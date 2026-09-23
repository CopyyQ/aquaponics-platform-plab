from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.exceptions import ApplicationError
from app.db.session import get_db
from app.models.device import Device
from app.models.project import Project
from app.models.user import User
from app.schemas.project_scenario import (
    ProjectScenarioActivationRead,
    ProjectScenarioBranchCreate,
    ProjectScenarioBranchRead,
    ProjectScenarioBranchUpdate,
    ProjectScenarioCloneRequest,
    ProjectScenarioCreate,
    ProjectScenarioDetailRead,
    ProjectScenarioItemRead,
    ProjectScenarioItemUpdate,
    ProjectScenarioMetadataUpdate,
    ProjectScenarioSummaryRead,
)
from app.services.access_service import require_project_access
from app.services.project_activity_service import record_project_activity
from app.services.project_scenario_service import (
    activate_project_scenario,
    clone_project_scenario,
    create_project_scenario,
    create_project_scenario_branch,
    get_project_scenario,
    get_project_scenario_branch,
    get_project_scenario_item,
    list_project_scenarios,
    project_scenario_branch_read,
    project_scenario_item_read,
    retire_project_scenario,
    retire_project_scenario_branch,
    scenario_detail_read,
    scenario_summary_read,
    update_project_scenario_branch,
    update_project_scenario_item,
    update_project_scenario_metadata,
)
from app.services.public_identity_service import (
    PublicIdentityNotFoundError,
    get_device_by_public_id,
    get_system_by_public_id,
)

router = APIRouter(
    prefix="/aquaponics-systems/{system_id}/devices/{device_id}/scenarios",
    tags=["Device Scenarios"],
)


async def _device_for_actor(
    db: AsyncSession,
    *,
    system_id: UUID,
    device_id: UUID,
    actor: User,
    manage: bool,
) -> tuple[Project, Device]:
    try:
        project = await get_system_by_public_id(db, system_id)
    except PublicIdentityNotFoundError as exc:
        raise ApplicationError(
            "AQUAPONICS_SYSTEM_NOT_FOUND",
            "Không tìm thấy dự án",
            404,
        ) from exc

    project = await require_project_access(
        db,
        project.id,
        actor,
        manage=manage,
    )
    try:
        device = await get_device_by_public_id(db, project, device_id)
    except PublicIdentityNotFoundError as exc:
        raise ApplicationError(
            "DEVICE_NOT_FOUND",
            "Không tìm thấy thiết bị",
            404,
        ) from exc
    return project, device


@router.get("", response_model=list[ProjectScenarioSummaryRead])
async def list_device_scenarios(
    system_id: UUID,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.read")),
) -> list[ProjectScenarioSummaryRead]:
    _, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=False,
    )
    rows = await list_project_scenarios(db, device=device)
    return [scenario_summary_read(row) for row in rows]


@router.post(
    "",
    response_model=ProjectScenarioDetailRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_device_scenario(
    system_id: UUID,
    device_id: UUID,
    payload: ProjectScenarioCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.create")),
) -> ProjectScenarioDetailRead:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    scenario = await create_project_scenario(
        db,
        device=device,
        actor_id=actor.id,
        payload=payload,
    )
    action = (
        "PROJECT_SCENARIO_CLONED"
        if payload.clone_from_scenario_id is not None
        else "PROJECT_SCENARIO_CREATED"
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action=action,
        entity_type="PROJECT_SCENARIO",
        entity_id=scenario.id,
        entity_name=scenario.name,
        changes={
            "source_scenario_id": str(payload.clone_from_scenario_id)
            if payload.clone_from_scenario_id
            else None
        },
    )
    response = scenario_detail_read(scenario)
    await db.commit()
    return response


@router.get("/{scenario_id}", response_model=ProjectScenarioDetailRead)
async def get_device_scenario(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.read")),
) -> ProjectScenarioDetailRead:
    _, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=False,
    )
    scenario = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    return scenario_detail_read(scenario)


@router.patch("/{scenario_id}", response_model=ProjectScenarioDetailRead)
async def update_device_scenario(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    payload: ProjectScenarioMetadataUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.update")),
) -> ProjectScenarioDetailRead:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    scenario = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    before = {"name": scenario.name, "description": scenario.description}
    scenario = await update_project_scenario_metadata(
        db,
        scenario=scenario,
        actor_id=actor.id,
        payload=payload,
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_UPDATED",
        entity_type="PROJECT_SCENARIO",
        entity_id=scenario.id,
        entity_name=scenario.name,
        changes={
            "name": {"before": before["name"], "after": scenario.name},
            "description": {
                "before": before["description"],
                "after": scenario.description,
            },
        },
    )
    response = scenario_detail_read(scenario)
    await db.commit()
    return response


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_scenario(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.delete")),
) -> Response:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    scenario = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    await retire_project_scenario(
        db,
        scenario=scenario,
        actor_id=actor.id,
        retired_at=datetime.now(UTC),
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_RETIRED",
        entity_type="PROJECT_SCENARIO",
        entity_id=scenario.id,
        entity_name=scenario.name,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{scenario_id}/clone",
    response_model=ProjectScenarioDetailRead,
    status_code=status.HTTP_201_CREATED,
)
async def clone_device_scenario(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    payload: ProjectScenarioCloneRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.create")),
) -> ProjectScenarioDetailRead:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    source = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    clone = await clone_project_scenario(
        db,
        source=source,
        actor_id=actor.id,
        name=payload.name,
        description=payload.description,
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_CLONED",
        entity_type="PROJECT_SCENARIO",
        entity_id=clone.id,
        entity_name=clone.name,
        changes={"source_scenario_id": str(source.public_id)},
    )
    response = scenario_detail_read(clone)
    await db.commit()
    return response


@router.post(
    "/{scenario_id}/activate",
    response_model=ProjectScenarioActivationRead,
)
async def activate_device_scenario(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.activate")),
) -> ProjectScenarioActivationRead:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    target = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    previous_name = next(
        (
            row.name
            for row in await list_project_scenarios(db, device=device)
            if row.is_active
        ),
        None,
    )
    result = await activate_project_scenario(
        db,
        device=device,
        target=target,
        actor=actor,
        activated_at=datetime.now(UTC),
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_ACTIVATED",
        entity_type="PROJECT_SCENARIO",
        entity_id=target.id,
        entity_name=target.name,
        changes={
            "previous_scenario": previous_name,
            "new_scenario": target.name,
            "closed_incident_count": result.closed_incident_count,
        },
    )
    await db.commit()
    return result


@router.patch(
    "/{scenario_id}/items/{item_id}",
    response_model=ProjectScenarioItemRead,
)
async def update_device_scenario_item(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    item_id: UUID,
    payload: ProjectScenarioItemUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.update")),
) -> ProjectScenarioItemRead:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    scenario = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    item = await get_project_scenario_item(
        db,
        scenario=scenario,
        public_id=item_id,
    )
    item = await update_project_scenario_item(
        db,
        item=item,
        actor_id=actor.id,
        payload=payload,
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_UPDATED",
        entity_type="PROJECT_SCENARIO_ITEM",
        entity_id=item.id,
        entity_name=item.name,
        changes=payload.model_dump(exclude_unset=True),
    )
    response = project_scenario_item_read(item)
    await db.commit()
    return response


@router.post(
    "/{scenario_id}/items/{item_id}/branches",
    response_model=ProjectScenarioBranchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_device_scenario_branch(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    item_id: UUID,
    payload: ProjectScenarioBranchCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.update")),
) -> ProjectScenarioBranchRead:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    scenario = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    item = await get_project_scenario_item(
        db,
        scenario=scenario,
        public_id=item_id,
    )
    branch = await create_project_scenario_branch(
        db,
        item=item,
        actor_id=actor.id,
        payload=payload,
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_BRANCH_UPDATED",
        entity_type="PROJECT_SCENARIO_BRANCH",
        entity_id=branch.id,
        entity_name=branch.name,
        changes={"operation": "created"},
    )
    response = project_scenario_branch_read(branch)
    await db.commit()
    return response


@router.patch(
    "/{scenario_id}/items/{item_id}/branches/{branch_id}",
    response_model=ProjectScenarioBranchRead,
)
async def update_device_scenario_branch(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    item_id: UUID,
    branch_id: UUID,
    payload: ProjectScenarioBranchUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.update")),
) -> ProjectScenarioBranchRead:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    scenario = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    item = await get_project_scenario_item(
        db,
        scenario=scenario,
        public_id=item_id,
    )
    branch = await get_project_scenario_branch(
        db,
        item=item,
        public_id=branch_id,
    )
    branch = await update_project_scenario_branch(
        db,
        branch=branch,
        actor_id=actor.id,
        payload=payload,
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_BRANCH_UPDATED",
        entity_type="PROJECT_SCENARIO_BRANCH",
        entity_id=branch.id,
        entity_name=branch.name,
        changes=payload.model_dump(exclude_unset=True),
    )
    response = project_scenario_branch_read(branch)
    await db.commit()
    return response


@router.delete(
    "/{scenario_id}/items/{item_id}/branches/{branch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_device_scenario_branch(
    system_id: UUID,
    device_id: UUID,
    scenario_id: UUID,
    item_id: UUID,
    branch_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("project_scenarios.update")),
) -> Response:
    project, device = await _device_for_actor(
        db,
        system_id=system_id,
        device_id=device_id,
        actor=actor,
        manage=True,
    )
    scenario = await get_project_scenario(
        db,
        device=device,
        public_id=scenario_id,
    )
    item = await get_project_scenario_item(
        db,
        scenario=scenario,
        public_id=item_id,
    )
    branch = await get_project_scenario_branch(
        db,
        item=item,
        public_id=branch_id,
    )
    await retire_project_scenario_branch(
        db,
        branch=branch,
        actor_id=actor.id,
        retired_at=datetime.now(UTC),
    )
    await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_SCENARIO_BRANCH_UPDATED",
        entity_type="PROJECT_SCENARIO_BRANCH",
        entity_id=branch.id,
        entity_name=branch.name,
        changes={"operation": "retired"},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
