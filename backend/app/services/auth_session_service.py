from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserStatus
from app.core.exceptions import ApplicationError
from app.core.security import create_access_token
from app.models.auth_session import UserSession
from app.models.user import User


@dataclass(frozen=True)
class IssuedSession:
    session: UserSession
    user: User
    access_token: str
    refresh_secret: str
    cookie_value: str
    max_age_seconds: int


def generate_refresh_secret() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def build_refresh_cookie_value(session_id: UUID, secret: str) -> str:
    return f"{session_id}.{secret}"


def parse_refresh_cookie_value(value: str) -> tuple[UUID, str]:
    raw_id, separator, secret = value.partition(".")
    if not separator or not secret:
        raise ValueError("Malformed refresh cookie")
    return UUID(raw_id), secret


def _metadata_hash(kind: str, value: str | None) -> str | None:
    if not value:
        return None
    message = f"auth-session:{kind}:{value}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def _invalid_session_error() -> ApplicationError:
    return ApplicationError(
        "INVALID_SESSION",
        "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
        401,
    )


def _access_token(user: User, session: UserSession) -> str:
    return create_access_token(
        str(user.id),
        {
            "sid": str(session.public_id),
            "jti": uuid4().hex,
            "role": user.system_role.value,
            "token_version": user.token_version,
        },
    )


def _issued(
    *,
    user: User,
    session: UserSession,
    refresh_secret: str,
    now: datetime,
) -> IssuedSession:
    return IssuedSession(
        session=session,
        user=user,
        access_token=_access_token(user, session),
        refresh_secret=refresh_secret,
        cookie_value=build_refresh_cookie_value(session.public_id, refresh_secret),
        max_age_seconds=max(0, int((session.expires_at - now).total_seconds())),
    )


async def create_user_session(
    db: AsyncSession,
    *,
    user: User,
    client_ip: str | None,
    user_agent: str | None,
    now: datetime | None = None,
) -> IssuedSession:
    timestamp = now or datetime.now(UTC)
    refresh_secret = generate_refresh_secret()
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_secret(refresh_secret),
        created_at=timestamp,
        expires_at=timestamp + timedelta(days=settings.auth_session_days),
        ip_hash=_metadata_hash("ip", client_ip),
        user_agent_hash=_metadata_hash("user-agent", user_agent),
    )
    db.add(session)
    await db.flush()
    return _issued(
        user=user,
        session=session,
        refresh_secret=refresh_secret,
        now=timestamp,
    )


async def rotate_user_session(
    db: AsyncSession,
    *,
    cookie_value: str,
    now: datetime | None = None,
) -> IssuedSession:
    timestamp = now or datetime.now(UTC)
    try:
        session_id, refresh_secret = parse_refresh_cookie_value(cookie_value)
    except (TypeError, ValueError) as exc:
        raise _invalid_session_error() from exc

    session = await db.scalar(
        select(UserSession)
        .where(UserSession.public_id == session_id)
        .with_for_update()
    )
    if session is None or session.revoked_at is not None or session.expires_at <= timestamp:
        raise _invalid_session_error()

    expected_hash = hash_refresh_secret(refresh_secret)
    if not hmac.compare_digest(session.refresh_token_hash, expected_hash):
        session.revoked_at = timestamp
        session.revoke_reason = "REFRESH_TOKEN_REPLAY"
        await db.commit()
        raise _invalid_session_error()

    user = await db.get(User, session.user_id)
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or user.is_deleted
        or user.deleted_at is not None
    ):
        raise _invalid_session_error()

    new_secret = generate_refresh_secret()
    session.refresh_token_hash = hash_refresh_secret(new_secret)
    session.last_refreshed_at = timestamp
    await db.flush()
    return _issued(
        user=user,
        session=session,
        refresh_secret=new_secret,
        now=timestamp,
    )


async def revoke_session_from_cookie(
    db: AsyncSession,
    *,
    cookie_value: str,
    reason: str,
    now: datetime | None = None,
) -> bool:
    timestamp = now or datetime.now(UTC)
    try:
        session_id, refresh_secret = parse_refresh_cookie_value(cookie_value)
    except (TypeError, ValueError):
        return False

    session = await db.scalar(
        select(UserSession)
        .where(UserSession.public_id == session_id)
        .with_for_update()
    )
    if session is None:
        return False
    if not hmac.compare_digest(
        session.refresh_token_hash,
        hash_refresh_secret(refresh_secret),
    ):
        return False
    if session.revoked_at is None:
        session.revoked_at = timestamp
        session.revoke_reason = reason
        await db.flush()
    return True


async def revoke_user_sessions(
    db: AsyncSession,
    user_id: int,
    reason: str,
    *,
    now: datetime | None = None,
) -> int:
    timestamp = now or datetime.now(UTC)
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=timestamp, revoke_reason=reason)
    )
    return int(result.rowcount or 0)


async def revoke_session(
    db: AsyncSession,
    session: UserSession,
    reason: str,
    *,
    now: datetime | None = None,
) -> None:
    if session.revoked_at is not None:
        return
    session.revoked_at = now or datetime.now(UTC)
    session.revoke_reason = reason
    await db.flush()
