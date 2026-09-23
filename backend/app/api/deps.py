from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserStatus
from app.core.exceptions import ApplicationError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.auth_session import UserSession
from app.models.user import User
from app.services.permission_service import has_permission
from app.services.public_identity_service import (
    PublicIdentityNotFoundError,
    get_system_by_public_id,
)


bearer_scheme = HTTPBearer(auto_error=False)


def _inactive_account_error(
    user: User,
) -> ApplicationError:
    if user.status == UserStatus.DISABLED:
        return ApplicationError(
            "ACCOUNT_DISABLED",
            "Tài khoản đã bị vô hiệu hóa.",
            401,
        )

    if user.status == UserStatus.LOCKED:
        return ApplicationError(
            "ACCOUNT_LOCKED",
            "Tài khoản đang bị khóa.",
            401,
        )

    if (
        user.status == UserStatus.SOFT_DELETED
        or user.is_deleted
        or user.deleted_at is not None
    ):
        return ApplicationError(
            "ACCOUNT_DELETED",
            "Tài khoản đã bị xóa.",
            401,
        )

    return ApplicationError(
        "ACCOUNT_INACTIVE",
        "Tài khoản đã bị vô hiệu hóa hoặc khóa.",
        401,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise ApplicationError(
            "AUTHENTICATION_REQUIRED",
            "Chưa đăng nhập.",
            401,
        )

    try:
        payload = decode_access_token(
            credentials.credentials
        )
        user_id = int(payload["sub"])
        session_id = UUID(str(payload["sid"]))
        token_version = int(
            payload.get("token_version", -1)
        )
    except (
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise ApplicationError(
            "INVALID_TOKEN",
            "Token không hợp lệ hoặc đã hết hạn.",
            401,
        ) from exc

    row = (
        await db.execute(
            select(User, UserSession)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                User.id == user_id,
                UserSession.public_id == session_id,
            )
        )
    ).one_or_none()

    if row is None:
        raise ApplicationError(
            "TOKEN_REVOKED",
            "Phiên đăng nhập đã hết hiệu lực.",
            401,
        )

    user, auth_session = row
    if (
        user.status != UserStatus.ACTIVE
        or user.is_deleted
        or user.deleted_at is not None
    ):
        raise _inactive_account_error(user)

    if (
        user.token_version != token_version
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= datetime.now(UTC)
    ):
        raise ApplicationError(
            "TOKEN_REVOKED",
            "Phiên đăng nhập đã hết hiệu lực.",
            401,
        )

    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    if (
        user.status != UserStatus.ACTIVE
        or user.is_deleted
        or user.deleted_at is not None
    ):
        raise _inactive_account_error(user)

    return user


async def get_current_operational_user(
    user: User = Depends(
        get_current_active_user
    ),
) -> User:
    if user.must_change_password:
        raise ApplicationError(
            "PASSWORD_CHANGE_REQUIRED",
            "Bạn phải thay đổi mật khẩu trước khi tiếp tục.",
            403,
        )

    return user


# Dành cho endpoint đổi mật khẩu bắt buộc.
get_authenticated_user = get_current_active_user


def require_permission(permission_code: str):
    async def dependency(
        request: Request,
        user: User = Depends(get_current_operational_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        raw_system_id = request.path_params.get("system_id")
        system_id = None
        if raw_system_id is not None:
            try:
                system = await get_system_by_public_id(
                    db,
                    UUID(str(raw_system_id)),
                )
            except (
                ValueError,
                PublicIdentityNotFoundError,
            ) as exc:
                raise ApplicationError(
                    "AQUAPONICS_SYSTEM_NOT_FOUND",
                    "Aquaponics System không tồn tại",
                    404,
                ) from exc
            system_id = system.id
        if not await has_permission(
            db,
            user,
            permission_code,
            system_id,
        ):
            raise ApplicationError(
                "PERMISSION_REQUIRED",
                "Tài khoản không có quyền thực hiện thao tác này.",
                403,
            )
        return user

    return dependency
