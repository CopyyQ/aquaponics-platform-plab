from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.api.v1.auth import change_password
from app.api.v1.canonical_extensions import (
    ManagedPasswordUpdate,
    _set_lifecycle,
    force_logout_user,
    set_user_password,
)
from app.core.enums import UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.auth_session import UserSession
from app.models.audit_log import AuditLog
from app.models.permission import Role
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest
from app.schemas.user import AdminSetPasswordRequest, ResetPasswordRequest
from app.services.auth_session_service import create_user_session
from app.services.password_service import (
    admin_reset_user_password,
    admin_set_user_password,
)


@pytest_asyncio.fixture
async def revocation_users():
    suffix = uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        viewer_role = await db.scalar(select(Role).where(Role.code == "VIEWER"))
        admin = await db.scalar(select(User).where(User.username == "admin"))
        assert viewer_role is not None and admin is not None
        target = User(
            username=f"revoke-target-{suffix}",
            password_hash=hash_password("CurrentPassword@123"),
            full_name="Revocation target",
            email=f"revoke-target-{suffix}@example.com",
            phone_number=f"092{suffix[:7]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        other = User(
            username=f"revoke-other-{suffix}",
            password_hash=hash_password("OtherPassword@123"),
            full_name="Revocation other",
            email=f"revoke-other-{suffix}@example.com",
            phone_number=f"093{suffix[:7]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add_all([target, other])
        await db.flush()
        target_ids = (target.id, other.id)
        await create_user_session(
            db,
            user=target,
            client_ip="127.0.0.1",
            user_agent="pytest-revocation-1",
        )
        await create_user_session(
            db,
            user=target,
            client_ip="127.0.0.2",
            user_agent="pytest-revocation-2",
        )
        await create_user_session(
            db,
            user=other,
            client_ip="127.0.0.3",
            user_agent="pytest-revocation-other",
        )
        await db.commit()
        target_public_id = target.public_id
        other_public_id = other.public_id

    yield target_ids[0], target_public_id, target_ids[1], other_public_id, admin.id

    async with AsyncSessionLocal() as db:
        await db.execute(delete(UserSession).where(UserSession.user_id.in_(target_ids)))
        await db.execute(delete(AuditLog).where(AuditLog.user_id.in_(target_ids)))
        await db.execute(delete(User).where(User.id.in_(target_ids)))
        await db.commit()


async def _sessions(user_id: int) -> list[UserSession]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.scalars(
                    select(UserSession)
                    .where(UserSession.user_id == user_id)
                    .order_by(UserSession.id)
                )
            ).all()
        )


@pytest.mark.asyncio
async def test_self_password_change_revokes_all_sessions_and_not_other_user(
    revocation_users,
) -> None:
    target_id, _target_public_id, other_id, _other_public_id, _admin_id = revocation_users
    async with AsyncSessionLocal() as db:
        target = await db.get(User, target_id)
        assert target is not None
        await change_password(
            ChangePasswordRequest(
                current_password="CurrentPassword@123",
                new_password="NewPassword@123",
                confirm_password="NewPassword@123",
            ),
            target,
            db,
        )

    target_sessions = await _sessions(target_id)
    other_sessions = await _sessions(other_id)
    assert target_sessions
    assert all(row.revoked_at is not None for row in target_sessions)
    assert {row.revoke_reason for row in target_sessions} == {"PASSWORD_CHANGED"}
    assert all(row.revoked_at is None for row in other_sessions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_status", "reason"),
    [
        (UserStatus.DISABLED, "ACCOUNT_DISABLED"),
        (UserStatus.LOCKED, "ACCOUNT_LOCKED"),
        (UserStatus.SOFT_DELETED, "ACCOUNT_DELETED"),
    ],
)
async def test_inactive_lifecycle_revokes_existing_sessions(
    revocation_users,
    target_status: UserStatus,
    reason: str,
) -> None:
    target_id, _target_public_id, _other_id, _other_public_id, admin_id = revocation_users
    async with AsyncSessionLocal() as db:
        target = await db.get(User, target_id)
        admin = await db.get(User, admin_id)
        assert target is not None and admin is not None
        await _set_lifecycle(
            db,
            target,
            admin,
            target_status,
            f"TEST_{target_status.value}",
            "security regression",
        )

    sessions = await _sessions(target_id)
    assert sessions
    assert all(row.revoked_at is not None for row in sessions)
    assert {row.revoke_reason for row in sessions} == {reason}


@pytest.mark.asyncio
async def test_force_logout_revokes_all_server_sessions(revocation_users) -> None:
    target_id, target_public_id, _other_id, _other_public_id, admin_id = revocation_users
    async with AsyncSessionLocal() as db:
        admin = await db.get(User, admin_id)
        assert admin is not None
        await force_logout_user(target_public_id, db, admin)

    sessions = await _sessions(target_id)
    assert sessions
    assert all(row.revoked_at is not None for row in sessions)
    assert {row.revoke_reason for row in sessions} == {"FORCE_LOGOUT"}


@pytest.mark.asyncio
async def test_admin_set_password_with_invalidation_revokes_sessions(revocation_users) -> None:
    target_id, _target_public_id, _other_id, _other_public_id, admin_id = revocation_users
    async with AsyncSessionLocal() as db:
        target = await db.get(User, target_id)
        admin = await db.get(User, admin_id)
        assert target is not None and admin is not None
        result = await admin_set_user_password(
            db,
            user=target,
            payload=AdminSetPasswordRequest(
                new_password="AdminChanged@123",
                confirm_password="AdminChanged@123",
                invalidate_sessions=True,
                must_change_password=False,
            ),
            actor=admin,
        )

    assert result.sessions_invalidated is True
    sessions = await _sessions(target_id)
    assert sessions
    assert all(row.revoked_at is not None for row in sessions)
    assert {row.revoke_reason for row in sessions} == {"PASSWORD_CHANGED"}


@pytest.mark.asyncio
async def test_admin_reset_password_revokes_sessions(revocation_users) -> None:
    target_id, _target_public_id, _other_id, _other_public_id, admin_id = revocation_users
    async with AsyncSessionLocal() as db:
        target = await db.get(User, target_id)
        admin = await db.get(User, admin_id)
        assert target is not None and admin is not None
        await admin_reset_user_password(
            db,
            user=target,
            payload=ResetPasswordRequest(
                temporary_password="Temporary@123",
                confirm_password="Temporary@123",
                invalidate_sessions=True,
            ),
            actor=admin,
        )

    sessions = await _sessions(target_id)
    assert sessions
    assert all(row.revoked_at is not None for row in sessions)
    assert {row.revoke_reason for row in sessions} == {"PASSWORD_RESET"}


@pytest.mark.asyncio
async def test_canonical_set_password_revokes_sessions_when_requested(revocation_users) -> None:
    target_id, target_public_id, _other_id, _other_public_id, admin_id = revocation_users
    async with AsyncSessionLocal() as db:
        admin = await db.get(User, admin_id)
        assert admin is not None
        await set_user_password(
            target_public_id,
            ManagedPasswordUpdate(
                new_password="CanonicalChanged@123",
                confirm_password="CanonicalChanged@123",
                invalidate_sessions=True,
                must_change_password=False,
            ),
            db,
            admin,
        )

    sessions = await _sessions(target_id)
    assert sessions
    assert all(row.revoked_at is not None for row in sessions)
    assert {row.revoke_reason for row in sessions} == {"PASSWORD_CHANGED"}
