from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.client_ip import resolve_request_client_ip
from app.api.deps import _inactive_account_error, get_authenticated_user
from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead, UserSelfUpdate
from app.services.audit_service import write_audit
from app.services.auth_session_service import (
    create_user_session,
    revoke_session_from_cookie,
    revoke_user_sessions,
    rotate_user_session,
)
from app.services.login_rate_limit_service import (
    precheck_login_rate_limit,
    record_login_failure,
    record_login_success,
)
from app.services.permission_service import get_effective_permissions


router = APIRouter(prefix="/auth", tags=["Authentication"])
_DUMMY_PASSWORD_HASH = hash_password("invalid-login-dummy-password")


class SessionRead(BaseModel):
    user: UserRead
    permissions: list[str]


def _require_allowed_auth_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise ApplicationError(
            "AUTH_ORIGIN_REJECTED",
            "Nguồn yêu cầu không được phép.",
            403,
        )


def _set_refresh_cookie(response: Response, value: str, max_age: int) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        value,
        max_age=max_age,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path=f"{settings.api_v1_prefix}/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=f"{settings.api_v1_prefix}/auth",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    _require_allowed_auth_origin(request)
    client_ip = resolve_request_client_ip(request)
    await precheck_login_rate_limit(db, payload.username, client_ip)

    user = await db.scalar(
        select(User).where(User.username == payload.username)
    )
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, password_hash)
    if user is None or not password_valid:
        await record_login_failure(db, payload.username, client_ip)
        raise ApplicationError(
            "INVALID_CREDENTIALS",
            "Tên đăng nhập hoặc mật khẩu không đúng",
            401,
        )
    if (
        user.status.value != "ACTIVE"
        or user.is_deleted
        or user.deleted_at is not None
    ):
        raise _inactive_account_error(user)

    await record_login_success(db, payload.username, client_ip)
    user.last_login_at = datetime.now(UTC)
    issued = await create_user_session(
        db,
        user=user,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    await write_audit(
        db,
        user_id=user.id,
        action="LOGIN",
        entity_type="USER",
        entity_id=user.id,
    )
    await db.commit()
    _set_refresh_cookie(response, issued.cookie_value, issued.max_age_seconds)
    return TokenResponse(
        access_token=issued.access_token,
        must_change_password=user.must_change_password,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    _require_allowed_auth_origin(request)
    cookie_value = request.cookies.get(settings.refresh_cookie_name)
    if not cookie_value:
        _clear_refresh_cookie(response)
        raise ApplicationError(
            "INVALID_SESSION",
            "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            401,
        )

    issued = await rotate_user_session(
        db,
        cookie_value=cookie_value,
    )
    await db.commit()
    _set_refresh_cookie(response, issued.cookie_value, issued.max_age_seconds)
    return TokenResponse(
        access_token=issued.access_token,
        must_change_password=issued.user.must_change_password,
    )


@router.get("/session", response_model=SessionRead)
async def session(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    return SessionRead(
        user=UserRead.model_validate(user),
        permissions=sorted(
            await get_effective_permissions(db, user)
        ),
    )


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserSelfUpdate,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    old_data = {
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "address": user.address,
    }
    for key, value in payload.model_dump(
        exclude_unset=True
    ).items():
        setattr(user, key, value)
    await write_audit(
        db,
        user_id=user.id,
        action="UPDATE_PROFILE",
        entity_type="USER",
        entity_id=user.id,
        old_data=old_data,
        new_data=payload.model_dump(
            exclude_unset=True,
            mode="json",
        ),
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/change-password",
    response_model=MessageResponse,
)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if not verify_password(
        payload.current_password,
        user.password_hash,
    ):
        raise ApplicationError(
            "CURRENT_PASSWORD_INVALID",
            "Mật khẩu hiện tại không đúng",
            400,
        )
    if verify_password(
        payload.new_password,
        user.password_hash,
    ):
        raise ApplicationError(
            "PASSWORD_REUSE_NOT_ALLOWED",
            "Mật khẩu mới không được trùng mật khẩu hiện tại",
            400,
        )
    user.password_hash = hash_password(
        payload.new_password
    )
    user.password_changed_at = datetime.now(UTC)
    user.must_change_password = False
    user.token_version += 1
    await revoke_user_sessions(db, user.id, "PASSWORD_CHANGED")
    await write_audit(
        db,
        user_id=user.id,
        action="CHANGE_PASSWORD",
        entity_type="USER",
        entity_id=user.id,
    )
    await db.commit()
    return MessageResponse(
        message="Đổi mật khẩu thành công"
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    _require_allowed_auth_origin(request)
    cookie_value = request.cookies.get(settings.refresh_cookie_name)
    if cookie_value:
        await revoke_session_from_cookie(
            db,
            cookie_value=cookie_value,
            reason="LOGOUT",
        )
        await db.commit()
    _clear_refresh_cookie(response)
    return MessageResponse(message="Đăng xuất thành công.")
