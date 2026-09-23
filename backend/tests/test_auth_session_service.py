from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.core.exceptions import ApplicationError
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.auth_session import UserSession
from app.models.user import User
from app.services.auth_session_service import (
    build_refresh_cookie_value,
    create_user_session,
    generate_refresh_secret,
    hash_refresh_secret,
    parse_refresh_cookie_value,
    revoke_user_sessions,
    rotate_user_session,
)


def test_refresh_cookie_helpers_round_trip() -> None:
    secret = generate_refresh_secret()
    assert len(secret) >= 48
    digest = hash_refresh_secret(secret)
    assert len(digest) == 64
    assert secret not in digest

    from uuid import uuid4

    session_id = uuid4()
    cookie = build_refresh_cookie_value(session_id, secret)
    parsed_id, parsed_secret = parse_refresh_cookie_value(cookie)
    assert parsed_id == session_id
    assert parsed_secret == secret


@pytest.mark.asyncio
async def test_create_session_stores_only_digest_and_binds_access_token() -> None:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert user is not None
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()

        now = datetime.now(UTC)
        issued = await create_user_session(
            db,
            user=user,
            client_ip="203.0.113.10",
            user_agent="pytest-agent",
            now=now,
        )
        await db.commit()

        assert issued.session.expires_at == now + timedelta(days=30)
        assert issued.session.refresh_token_hash == hash_refresh_secret(issued.refresh_secret)
        assert issued.refresh_secret not in issued.session.refresh_token_hash
        assert issued.session.ip_hash != "203.0.113.10"
        assert issued.session.user_agent_hash != "pytest-agent"
        payload = decode_access_token(issued.access_token)
        assert payload["sid"] == str(issued.session.public_id)
        assert int(payload["sub"]) == user.id

        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()


@pytest.mark.asyncio
async def test_refresh_rotation_is_non_sliding_and_old_secret_revokes_session() -> None:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert user is not None
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()

        created_at = datetime.now(UTC)
        issued = await create_user_session(
            db,
            user=user,
            client_ip="203.0.113.11",
            user_agent="pytest-agent",
            now=created_at,
        )
        await db.commit()
        original_cookie = issued.cookie_value
        original_expiry = issued.session.expires_at

        rotated = await rotate_user_session(
            db,
            cookie_value=original_cookie,
            now=created_at + timedelta(hours=1),
        )
        await db.commit()

        assert rotated.cookie_value != original_cookie
        assert rotated.session.expires_at == original_expiry
        assert rotated.session.last_refreshed_at == created_at + timedelta(hours=1)

        with pytest.raises(ApplicationError) as caught:
            await rotate_user_session(
                db,
                cookie_value=original_cookie,
                now=created_at + timedelta(hours=2),
            )
        assert caught.value.status_code == 401
        await db.refresh(rotated.session)
        assert rotated.session.revoked_at is not None
        assert rotated.session.revoke_reason == "REFRESH_TOKEN_REPLAY"

        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()


@pytest.mark.asyncio
async def test_expired_session_cannot_refresh_and_revoke_all_marks_active_sessions() -> None:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "codex-test-owner"))
        assert user is not None
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()

        now = datetime.now(UTC)
        expired = await create_user_session(
            db,
            user=user,
            client_ip="203.0.113.12",
            user_agent="pytest-agent",
            now=now - timedelta(days=31),
        )
        active = await create_user_session(
            db,
            user=user,
            client_ip="203.0.113.13",
            user_agent="pytest-agent",
            now=now,
        )
        await db.commit()

        with pytest.raises(ApplicationError) as caught:
            await rotate_user_session(db, cookie_value=expired.cookie_value, now=now)
        assert caught.value.status_code == 401

        count = await revoke_user_sessions(db, user.id, "TEST_REVOKE", now=now)
        await db.commit()
        assert count == 2

        rows = (
            await db.scalars(select(UserSession).where(UserSession.user_id == user.id))
        ).all()
        assert {row.revoke_reason for row in rows} == {"TEST_REVOKE"}
        assert all(row.revoked_at == now for row in rows)
        assert active.session.id in {row.id for row in rows}

        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()
