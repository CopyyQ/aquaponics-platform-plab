from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProjectStatus
from app.core.exceptions import ApplicationError
from app.models.project import Project
from app.models.user import User
from app.services.access_service import get_admin_project_for_lifecycle
from app.services.project_activity_service import (
    dispatch_project_activity,
    record_project_activity,
)


async def disable_project(
    db: AsyncSession,
    *,
    project_id: int,
    reason: str,
    actor: User,
) -> Project:
    project = await get_admin_project_for_lifecycle(
        db,
        project_id,
    )
    if project.status == ProjectStatus.DISABLED:
        raise ApplicationError(
            "AQUAPONICS_SYSTEM_ALREADY_DISABLED",
            "Dự án đã bị vô hiệu hóa",
            409,
        )
    old_status = project.status.value
    project.status = ProjectStatus.DISABLED
    project.disabled_at = datetime.now(UTC)
    project.disabled_by_user_id = actor.id
    project.disabled_reason = reason.strip()
    activity = await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_DISABLED",
        entity_type="PROJECT",
        entity_id=project.id,
        entity_name=project.name,
        changes={
            "status": {
                "before": old_status,
                "after": ProjectStatus.DISABLED.value,
            }
        },
    )
    await db.commit()
    await db.refresh(project)
    await dispatch_project_activity(
        db,
        activity_id=activity.id,
    )
    return project


async def activate_project(
    db: AsyncSession,
    *,
    project_id: int,
    actor: User,
) -> Project:
    project = await get_admin_project_for_lifecycle(
        db,
        project_id,
    )
    if project.status == ProjectStatus.ACTIVE:
        raise ApplicationError(
            "AQUAPONICS_SYSTEM_ALREADY_ACTIVE",
            "Dự án đang hoạt động",
            409,
        )
    old_status = project.status.value
    project.status = ProjectStatus.ACTIVE
    project.disabled_at = None
    project.disabled_by_user_id = None
    project.disabled_reason = None
    activity = await record_project_activity(
        db,
        project_id=project.id,
        actor=actor,
        action="PROJECT_ENABLED",
        entity_type="PROJECT",
        entity_id=project.id,
        entity_name=project.name,
        changes={
            "status": {
                "before": old_status,
                "after": ProjectStatus.ACTIVE.value,
            }
        },
    )
    await db.commit()
    await db.refresh(project)
    await dispatch_project_activity(
        db,
        activity_id=activity.id,
    )
    return project
