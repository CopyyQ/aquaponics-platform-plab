"""Canonical compatibility surface for mature frontend capabilities.

These endpoints intentionally preserve the canonical public vocabulary while
re-exposing capabilities whose persistence/services survived the 0050 cleanup.
No /projects or /admin API families are reintroduced.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permission
from app.core.config import settings
from app.core.enums import UserStatus
from app.core.security import hash_password
from app.db.session import get_db
from app.models.permission import Role
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.operational_alert import NotificationDelivery, NotificationOutbox, OperationalIncident
from app.models.project_settings import (
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.notifications import (
    NotificationRecipientCreate,
    NotificationRecipientRead,
    NotificationRecipientUpdate,
    NotificationSettingsRead,
    NotificationSettingsUpdate,
    TestMessageResult,
)
from app.services.access_service import require_project_access
from app.services.audit_service import write_audit
from app.services.auth_session_service import revoke_user_sessions
from app.services.project_lifecycle_service import activate_project, disable_project
from app.services.aquaponics_system_creation_service import (
    AquaponicsSystemCreationError,
    create_aquaponics_system,
)
from app.services.project_role_service import remove_project_role_assignments
from app.services.telegram_notifier import TelegramNotifier
from app.services.public_identity_service import (
    PublicIdentityNotFoundError, get_system_by_public_id,
)

router = APIRouter()

class AquaponicsSystemLifecycleRead(BaseModel):
    id: UUID
    code: str
    name: str
    location: str | None
    description: str | None
    owner_user_id: UUID
    status: str


class AquaponicsSystemLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=1000)


class AlertDeliveryHistoryItem(BaseModel):
    id: int
    system_id: UUID
    created_at: datetime
    incident_id: int | None
    alert_id: int | None
    event_type: str
    risk: str | None
    channel: str
    recipient_id: int | None
    recipient_name: str
    status: str
    attempt_count: int
    skip_reason: str | None
    error_code: str | None
    error_message: str | None
    attempted_at: datetime | None
    sent_at: datetime | None
    reason: str | None


class RoleRead(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    is_system: bool
    enabled: bool


class UserAquaponicsSystemRead(BaseModel):
    id: UUID
    code: str
    name: str
    owner_user_id: UUID
    device_template_id: int | None
    scenario_catalog_id: int | None
    location: str | None
    status: str
    role: str
    relationship: str


class UserAquaponicsSystemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_template_id: int = Field(gt=0)
    scenario_catalog_id: int = Field(gt=0)


class AquaponicsSystemOwnerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID


def _creation_error(exc: AquaponicsSystemCreationError) -> HTTPException:
    return HTTPException(exc.status_code, {"code": exc.code, "detail": exc.message})


class ManagedUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone_number: str = Field(min_length=8, max_length=30)
    address: str = Field(default="", max_length=2000)
    role_id: int | None = None
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    must_change_password: bool = True


class ManagedUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    phone_number: str | None = Field(default=None, min_length=8, max_length=30)
    address: str | None = None
    role_id: int | None = None


class ManagedUserRead(BaseModel):
    id: UUID
    username: str
    full_name: str
    email: str
    phone_number: str
    address: str
    role_id: int | None
    role_code: str | None
    role_name: str | None
    status: UserStatus
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    disabled_reason: str | None
    locked_reason: str | None


class ManagedPasswordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    invalidate_sessions: bool = True
    must_change_password: bool = False


class AccountLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=1000)


def _managed_user(row: User) -> ManagedUserRead:
    return ManagedUserRead(
        id=row.public_id,
        username=row.username,
        full_name=row.full_name,
        email=row.email,
        phone_number=row.phone_number,
        address=row.address,
        role_id=row.role_id,
        role_code=row.role.code if row.role else None,
        role_name=row.role.name if row.role else None,
        status=row.status,
        must_change_password=row.must_change_password,
        last_login_at=row.last_login_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        disabled_reason=row.disabled_reason,
        locked_reason=row.locked_reason,
    )


async def _managed_user_row(db: AsyncSession, user_id: UUID, *, include_deleted: bool = True) -> User:
    query = select(User).options(selectinload(User.role)).where(User.public_id == user_id)
    if not include_deleted:
        query = query.where(User.is_deleted.is_(False))
    row = await db.scalar(query)
    if row is None:
        raise HTTPException(404, "Không tìm thấy User")
    return row


async def _system_row(db: AsyncSession, system_id: UUID, actor: User, *, manage: bool = False) -> Project:
    try:
        system = await get_system_by_public_id(db, system_id)
    except PublicIdentityNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return await require_project_access(db, system.id, actor, manage=manage)


def _lifecycle_read(system: Project) -> AquaponicsSystemLifecycleRead:
    return AquaponicsSystemLifecycleRead(id=system.public_id, code=system.code, name=system.name,
        location=system.location, description=system.description, owner_user_id=system.owner.public_id,
        status=system.status.value)


@router.post("/aquaponics-systems/{system_id}/lifecycle/disable", response_model=AquaponicsSystemLifecycleRead, tags=["Aquaponics Systems"])
async def disable_system(
    system_id: UUID,
    payload: AquaponicsSystemLifecycleRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("aquaponics_systems.manage_all")),
):
    reason = (payload.reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(422, "Cần nhập lý do ít nhất 3 ký tự")
    system = await _system_row(db, system_id, actor, manage=True)
    result = await disable_project(db, project_id=system.id, reason=reason, actor=actor)
    await db.refresh(result, attribute_names=["owner"])
    return _lifecycle_read(result)


@router.post("/aquaponics-systems/{system_id}/lifecycle/activate", response_model=AquaponicsSystemLifecycleRead, tags=["Aquaponics Systems"])
async def activate_system(
    system_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("aquaponics_systems.manage_all")),
):
    system = await _system_row(db, system_id, actor, manage=True)
    result = await activate_project(db, project_id=system.id, actor=actor)
    await db.refresh(result, attribute_names=["owner"])
    return _lifecycle_read(result)


@router.get("/roles", response_model=list[RoleRead], tags=["Roles"])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("roles.read")),
) -> list[RoleRead]:
    rows = (await db.scalars(select(Role).where(Role.enabled.is_(True)).order_by(Role.name))).all()
    return [RoleRead(id=r.id, code=r.code, name=r.name, description=r.description, is_system=r.is_system, enabled=r.enabled) for r in rows]


@router.get("/users/{user_id}/aquaponics-systems", response_model=list[UserAquaponicsSystemRead], tags=["Users"])
async def list_user_aquaponics_systems(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("users.read")),
) -> list[UserAquaponicsSystemRead]:
    user = await _managed_user_row(db, user_id)
    owned = (await db.scalars(select(Project).options(selectinload(Project.owner)).where(
        Project.owner_user_id == user.id, Project.is_deleted.is_(False)
    ).order_by(Project.name))).all()
    return [UserAquaponicsSystemRead(id=row.public_id, code=row.code, name=row.name,
        owner_user_id=row.owner.public_id, device_template_id=row.device_template_id,
        scenario_catalog_id=row.scenario_catalog_id, location=row.location,
        status=row.status.value, role="OWNER", relationship="OWNER") for row in owned]


@router.post("/users/{user_id}/aquaponics-systems", response_model=UserAquaponicsSystemRead, status_code=201, tags=["Users"])
async def create_user_aquaponics_system(
    user_id: UUID,
    payload: UserAquaponicsSystemCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("aquaponics_systems.manage_all")),
) -> UserAquaponicsSystemRead:
    try:
        owner = await _managed_user_row(db, user_id, include_deleted=False)
        system = await create_aquaponics_system(
            db,
            owner_user_id=owner.id,
            actor_id=actor.id,
            device_template_id=payload.device_template_id,
            scenario_catalog_id=payload.scenario_catalog_id,
        )
    except AquaponicsSystemCreationError as exc:
        raise _creation_error(exc) from exc
    return UserAquaponicsSystemRead(id=system.public_id, code=system.code, name=system.name,
        owner_user_id=owner.public_id, device_template_id=system.device_template_id,
        scenario_catalog_id=system.scenario_catalog_id, location=system.location,
        status=system.status.value, role="OWNER", relationship="OWNER")


@router.put("/aquaponics-systems/{system_id}/owner", response_model=AquaponicsSystemLifecycleRead, tags=["Aquaponics Systems"])
async def transfer_aquaponics_system_owner(
    system_id: UUID,
    payload: AquaponicsSystemOwnerUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("aquaponics_systems.manage_all")),
) -> AquaponicsSystemLifecycleRead:
    system = await _system_row(db, system_id, actor, manage=True)
    target = await _managed_user_row(db, payload.user_id, include_deleted=False)
    if target.status != UserStatus.ACTIVE:
        raise HTTPException(422, "Tài khoản nhận quyền sở hữu phải đang hoạt động")
    if target.id != system.owner_user_id and await db.scalar(
        select(Project.id).where(Project.owner_user_id == target.id)
    ):
        raise HTTPException(409, "Người dùng này đã sở hữu một Hệ thống Aquaponics")
    old_owner_id = system.owner_user_id
    system.owner_user_id = target.id
    membership = await db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == system.id, ProjectMember.user_id == target.id
    ))
    if membership is not None:
        await remove_project_role_assignments(db, user_id=target.id, system_id=system.id)
        await db.delete(membership)
    await write_audit(db, user_id=actor.id, project_id=system.id,
        action="TRANSFER_AQUAPONICS_SYSTEM_OWNER", entity_type="AQUAPONICS_SYSTEM", entity_id=system.id,
        old_data={"owner_user_id": old_owner_id}, new_data={"owner_user_id": target.id})
    await db.commit()
    await db.refresh(system, attribute_names=["owner"])
    return _lifecycle_read(system)


@router.post("/users", response_model=ManagedUserRead, status_code=201, tags=["Users"])
async def create_user(
    payload: ManagedUserCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("users.create")),
) -> ManagedUserRead:
    if payload.password != payload.confirm_password:
        raise HTTPException(422, "Mật khẩu xác nhận không trùng khớp")
    if payload.role_id is not None and await db.get(Role, payload.role_id) is None:
        raise HTTPException(422, "Role không tồn tại")
    if await db.scalar(select(User.id).where((User.username == payload.username) | (User.email == str(payload.email)) | (User.phone_number == payload.phone_number))):
        raise HTTPException(409, "Tên đăng nhập, email hoặc số điện thoại đã tồn tại")
    row = User(
        username=payload.username.strip(),
        full_name=payload.full_name.strip(),
        email=str(payload.email).strip().lower(),
        phone_number=payload.phone_number.strip(),
        address=payload.address.strip(),
        role_id=payload.role_id,
        password_hash=hash_password(payload.password),
        must_change_password=payload.must_change_password,
        status=UserStatus.ACTIVE,
        created_by=actor.id,
    )
    db.add(row)
    await db.flush()
    await write_audit(db, user_id=actor.id, action="CREATE_USER", entity_type="USER", entity_id=row.id, new_data={"role_id": row.role_id})
    await db.commit()
    return _managed_user(await _managed_user_row(db, row.public_id))


@router.patch("/users/{user_id}", response_model=ManagedUserRead, tags=["Users"])
async def update_user(
    user_id: UUID,
    payload: ManagedUserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("users.update")),
) -> ManagedUserRead:
    row = await _managed_user_row(db, user_id, include_deleted=False)
    if payload.role_id is not None and await db.get(Role, payload.role_id) is None:
        raise HTTPException(422, "Role không tồn tại")
    values = payload.model_dump(exclude_unset=True)
    old = {k: getattr(row, k) for k in values}
    for key, value in values.items():
        setattr(row, key, str(value).strip().lower() if key == "email" and value is not None else value)
    await write_audit(db, user_id=actor.id, action="UPDATE_USER", entity_type="USER", entity_id=row.id, old_data=old, new_data=values)
    await db.commit()
    return _managed_user(await _managed_user_row(db, row.public_id))


@router.post("/users/{user_id}/password", response_model=MessageResponse, tags=["Users"])
async def set_user_password(
    user_id: UUID,
    payload: ManagedPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("users.set_password")),
) -> MessageResponse:
    if payload.new_password != payload.confirm_password:
        raise HTTPException(422, "Mật khẩu xác nhận không trùng khớp")
    row = await _managed_user_row(db, user_id, include_deleted=False)
    row.password_hash = hash_password(payload.new_password)
    row.password_changed_at = datetime.now(UTC)
    row.must_change_password = payload.must_change_password
    if payload.invalidate_sessions:
        row.token_version += 1
        await revoke_user_sessions(db, row.id, "PASSWORD_CHANGED")
    await write_audit(db, user_id=actor.id, action="SET_USER_PASSWORD", entity_type="USER", entity_id=row.id, new_data={"sessions_invalidated": payload.invalidate_sessions, "must_change_password": payload.must_change_password})
    await db.commit()
    return MessageResponse(message="Đã cập nhật mật khẩu")


async def _set_lifecycle(db: AsyncSession, row: User, actor: User, target: UserStatus, action: str, reason: str | None) -> None:
    now = datetime.now(UTC)
    if target == UserStatus.SOFT_DELETED:
        row.is_deleted = True
        row.deleted_at = now
    else:
        row.is_deleted = False
        row.deleted_at = None
    row.status = target
    if target == UserStatus.DISABLED:
        row.disabled_at, row.disabled_by_user_id, row.disabled_reason = now, actor.id, reason
        row.locked_at = row.locked_by_user_id = row.locked_reason = None
    elif target == UserStatus.LOCKED:
        row.locked_at, row.locked_by_user_id, row.locked_reason = now, actor.id, reason
    elif target == UserStatus.ACTIVE:
        row.disabled_at = row.disabled_by_user_id = row.disabled_reason = None
        row.locked_at = row.locked_by_user_id = row.locked_reason = None
    row.token_version += 1
    revoke_reason = {
        UserStatus.DISABLED: "ACCOUNT_DISABLED",
        UserStatus.LOCKED: "ACCOUNT_LOCKED",
        UserStatus.SOFT_DELETED: "ACCOUNT_DELETED",
    }.get(target)
    if revoke_reason is not None:
        await revoke_user_sessions(db, row.id, revoke_reason)
    await write_audit(db, user_id=actor.id, action=action, entity_type="USER", entity_id=row.id, new_data={"status": target.value, "reason": reason})
    await db.commit()


def lifecycle_route(path: str, permission: str, target: UserStatus, action: str, message: str):
    async def endpoint(
        user_id: UUID,
        payload: AccountLifecycleRequest | None = Body(default=None),
        db: AsyncSession = Depends(get_db),
        actor: User = Depends(require_permission(permission)),
    ) -> MessageResponse:
        row = await _managed_user_row(db, user_id)
        if row.id == actor.id and target != UserStatus.ACTIVE:
            raise HTTPException(409, "Không thể vô hiệu hóa tài khoản đang thao tác")
        await _set_lifecycle(db, row, actor, target, action, payload.reason if payload else None)
        return MessageResponse(message=message)
    router.add_api_route(path, endpoint, methods=["POST"], response_model=MessageResponse, tags=["Users"])


lifecycle_route("/users/{user_id}/activate", "users.update", UserStatus.ACTIVE, "ACTIVATE_USER", "Đã kích hoạt tài khoản")
lifecycle_route("/users/{user_id}/disable", "users.update", UserStatus.DISABLED, "DISABLE_USER", "Đã vô hiệu hóa tài khoản")
lifecycle_route("/users/{user_id}/lock", "users.lock", UserStatus.LOCKED, "LOCK_USER", "Đã khóa tài khoản")
lifecycle_route("/users/{user_id}/unlock", "users.unlock", UserStatus.ACTIVE, "UNLOCK_USER", "Đã mở khóa tài khoản")
lifecycle_route("/users/{user_id}/restore", "users.update", UserStatus.ACTIVE, "RESTORE_USER", "Đã khôi phục tài khoản")
lifecycle_route("/users/{user_id}/soft-delete", "users.delete", UserStatus.SOFT_DELETED, "SOFT_DELETE_USER", "Đã xóa mềm tài khoản")


@router.post("/users/{user_id}/force-logout", response_model=MessageResponse, tags=["Users"])
async def force_logout_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("users.force_logout")),
) -> MessageResponse:
    row = await _managed_user_row(db, user_id)
    row.token_version += 1
    await revoke_user_sessions(db, row.id, "FORCE_LOGOUT")
    await write_audit(db, user_id=actor.id, action="FORCE_LOGOUT_USER", entity_type="USER", entity_id=row.id)
    await db.commit()
    return MessageResponse(message="Đã thu hồi toàn bộ phiên đăng nhập")


async def _delivery_settings(db: AsyncSession, system_id: int) -> NotificationSettingsRead:
    item = await db.scalar(
        select(ProjectNotificationSettings).where(
            ProjectNotificationSettings.project_id == system_id
        )
    )
    recipients = list(
        (
            await db.scalars(
                select(ProjectNotificationRecipient)
                .where(ProjectNotificationRecipient.project_id == system_id)
                .order_by(ProjectNotificationRecipient.created_at)
            )
        ).all()
    )
    return NotificationSettingsRead(
        telegram_enabled=item.telegram_enabled if item else False,
        notify_alert_recovered=item.notify_alert_recovered if item else True,
        telegram_bot_configured=bool(
            settings.telegram_bot_token and settings.telegram_bot_token.strip()
        ),
        recipients=[NotificationRecipientRead.model_validate(x) for x in recipients],
    )


@router.get(
    "/aquaponics-systems/{system_id}/alert-delivery/settings",
    response_model=NotificationSettingsRead,
    tags=["Alert Delivery"],
)
async def get_delivery_settings(
    system_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("notifications.settings.read")),
) -> NotificationSettingsRead:
    internal_id = (await _system_row(db, system_id, actor)).id
    return await _delivery_settings(db, internal_id)


@router.put(
    "/aquaponics-systems/{system_id}/alert-delivery/settings",
    response_model=NotificationSettingsRead,
    tags=["Alert Delivery"],
)
async def update_delivery_settings(
    system_id: UUID,
    payload: NotificationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("notifications.settings.update")),
) -> NotificationSettingsRead:
    internal_id = (await _system_row(db, system_id, actor, manage=True)).id
    item = await db.scalar(
        select(ProjectNotificationSettings).where(
            ProjectNotificationSettings.project_id == internal_id
        )
    )
    if item is None:
        item = ProjectNotificationSettings(project_id=internal_id)
        db.add(item)
    item.telegram_enabled = payload.telegram_enabled
    item.notify_alert_recovered = payload.notify_alert_recovered
    await db.commit()
    return await _delivery_settings(db, internal_id)


async def _recipient(db: AsyncSession, system_id: int, recipient_id: int) -> ProjectNotificationRecipient:
    row = await db.scalar(select(ProjectNotificationRecipient).where(ProjectNotificationRecipient.id == recipient_id, ProjectNotificationRecipient.project_id == system_id))
    if row is None: raise HTTPException(404, "Không tìm thấy người nhận Telegram")
    return row


@router.post("/aquaponics-systems/{system_id}/alert-delivery/recipients", response_model=NotificationRecipientRead, status_code=201, tags=["Alert Delivery"])
async def add_recipient(system_id: UUID, payload: NotificationRecipientCreate, db: AsyncSession = Depends(get_db), actor: User = Depends(require_permission("notifications.recipients.create"))) -> ProjectNotificationRecipient:
    system_id = (await _system_row(db, system_id, actor, manage=True)).id
    row = ProjectNotificationRecipient(project_id=system_id, **payload.model_dump()); db.add(row)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback(); raise HTTPException(409, "Telegram Chat ID đã tồn tại") from exc
    await db.refresh(row); return row


@router.patch("/aquaponics-systems/{system_id}/alert-delivery/recipients/{recipient_id}", response_model=NotificationRecipientRead, tags=["Alert Delivery"])
async def update_recipient(system_id: UUID, recipient_id: int, payload: NotificationRecipientUpdate, db: AsyncSession = Depends(get_db), actor: User = Depends(require_permission("notifications.recipients.update"))) -> ProjectNotificationRecipient:
    system_id = (await _system_row(db, system_id, actor, manage=True)).id; row = await _recipient(db, system_id, recipient_id)
    for field, value in payload.model_dump(exclude_unset=True).items(): setattr(row, field, value)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback(); raise HTTPException(409, "Telegram Chat ID đã tồn tại") from exc
    await db.refresh(row); return row


@router.get("/aquaponics-systems/{system_id}/alert-delivery/recipients", response_model=list[NotificationRecipientRead], tags=["Alert Delivery"])
async def list_recipients(system_id: UUID, db: AsyncSession = Depends(get_db), actor: User = Depends(require_permission("notifications.recipients.read"))) -> list[ProjectNotificationRecipient]:
    system_id = (await _system_row(db, system_id, actor)).id
    return list((await db.scalars(select(ProjectNotificationRecipient).where(
        ProjectNotificationRecipient.project_id == system_id,
    ).order_by(ProjectNotificationRecipient.created_at))).all())


@router.delete("/aquaponics-systems/{system_id}/alert-delivery/recipients/{recipient_id}", status_code=204, tags=["Alert Delivery"])
async def delete_recipient(system_id: UUID, recipient_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(require_permission("notifications.recipients.delete"))) -> Response:
    system_id = (await _system_row(db, system_id, actor, manage=True)).id; await db.delete(await _recipient(db, system_id, recipient_id)); await db.commit(); return Response(status_code=204)


@router.post("/aquaponics-systems/{system_id}/alert-delivery/recipients/{recipient_id}/test", response_model=TestMessageResult, tags=["Alert Delivery"])
async def test_recipient(system_id: UUID, recipient_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(require_permission("notifications.recipients.test"))) -> TestMessageResult:
    system = await _system_row(db, system_id, actor, manage=True); row = await _recipient(db, system.id, recipient_id)
    if not row.enabled: raise HTTPException(409, "Người nhận đang tắt")
    result = await TelegramNotifier().send_message(row.telegram_chat_id, f"✅ Aquaponics Platform\n\nKết nối Telegram thành công.\n\nHệ thống: {system.name}\nNgười nhận: {row.name}")
    if not result.sent: raise HTTPException(503, "Không thể gửi tin nhắn thử qua Telegram")
    return TestMessageResult(sent=True, detail="Đã gửi tin nhắn thử")


@router.get("/aquaponics-systems/{system_id}/alert-delivery/history", response_model=list[AlertDeliveryHistoryItem], tags=["Alert Delivery"])
async def delivery_history(system_id: UUID, db: AsyncSession = Depends(get_db), actor: User = Depends(require_permission("notifications.history.read"))) -> list[AlertDeliveryHistoryItem]:
    system = await _system_row(db, system_id, actor); internal_system_id = system.id
    rows = (await db.execute(
        select(NotificationDelivery, NotificationOutbox, OperationalIncident, ProjectNotificationRecipient)
        .join(NotificationOutbox, NotificationOutbox.id == NotificationDelivery.outbox_id)
        .outerjoin(OperationalIncident, OperationalIncident.id == NotificationDelivery.incident_id)
        .outerjoin(ProjectNotificationRecipient, ProjectNotificationRecipient.id == NotificationDelivery.recipient_id)
        .where(NotificationOutbox.project_id == internal_system_id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(500)
    )).all()
    return [AlertDeliveryHistoryItem(
        id=delivery.id, system_id=system.public_id, created_at=delivery.created_at,
        incident_id=incident.id if incident else None, alert_id=incident.id if incident else None,
        event_type=outbox.event_type,
        risk=incident.business_risk_level_snapshot if incident else outbox.payload_snapshot.get("business_risk_level"),
        channel=delivery.channel, recipient_id=delivery.recipient_id,
        recipient_name=recipient.name if recipient else delivery.recipient_reference,
        status=delivery.status, attempt_count=delivery.attempt_count,
        skip_reason=outbox.skip_reason if delivery.status == "SKIPPED" else None,
        error_code=delivery.error_category, error_message=delivery.error_message,
        attempted_at=delivery.last_attempt_at, sent_at=delivery.sent_at,
        reason=delivery.error_category,
    ) for delivery, outbox, incident, recipient in rows]
