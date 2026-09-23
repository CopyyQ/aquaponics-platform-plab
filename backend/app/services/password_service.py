from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserStatus
from app.core.exceptions import ApplicationError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import (
    AdminSetPasswordRequest,
    AdminSetPasswordResponse,
    ResetPasswordRequest,
)
from app.services.audit_service import write_audit
from app.services.auth_session_service import revoke_user_sessions


async def admin_set_user_password(
    db: AsyncSession,
    *,
    user: User,
    payload: AdminSetPasswordRequest,
    actor: User,
) -> AdminSetPasswordResponse:
    if (
        user.is_deleted
        or user.deleted_at is not None
        or user.status == UserStatus.SOFT_DELETED
    ):
        raise ApplicationError(
            "ACCOUNT_RESTORE_REQUIRED",
            "Hãy khôi phục tài khoản trước khi đặt lại mật khẩu",
            409,
        )
    user.password_hash = hash_password(
        payload.new_password
    )
    user.password_changed_at = datetime.now(UTC)
    user.must_change_password = (
        payload.must_change_password
    )
    if payload.invalidate_sessions:
        user.token_version += 1
        await revoke_user_sessions(db, user.id, "PASSWORD_CHANGED")
    await write_audit(
        db,
        user_id=actor.id,
        action="ADMIN_SET_USER_PASSWORD",
        entity_type="USER",
        entity_id=user.id,
        new_data={
            "target_user_id": user.id,
            "sessions_invalidated": payload.invalidate_sessions,
            "must_change_password": payload.must_change_password,
        },
    )
    await db.commit()
    return AdminSetPasswordResponse(
        message="Đã cập nhật mật khẩu.",
        sessions_invalidated=payload.invalidate_sessions,
        must_change_password=payload.must_change_password,
    )


async def admin_reset_user_password(
    db: AsyncSession,
    *,
    user: User,
    payload: ResetPasswordRequest,
    actor: User,
) -> None:
    if not payload.passwords_match:
        raise ApplicationError(
            "PASSWORD_CONFIRMATION_MISMATCH",
            "Mật khẩu xác nhận không trùng khớp",
            422,
        )
    user.password_hash = hash_password(
        payload.temporary_password
    )
    user.must_change_password = True
    user.password_changed_at = datetime.now(UTC)
    user.token_version += 1
    await revoke_user_sessions(db, user.id, "PASSWORD_RESET")
    await write_audit(
        db,
        user_id=actor.id,
        action="RESET_PASSWORD",
        entity_type="USER",
        entity_id=user.id,
    )
    await db.commit()
