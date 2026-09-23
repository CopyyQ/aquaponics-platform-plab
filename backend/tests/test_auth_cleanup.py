from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.jobs.auth_cleanup import cleanup_auth_state
from app.models.auth_session import AuthRateLimitBucket, UserSession
from app.models.user import User


@pytest.mark.asyncio
async def test_auth_cleanup_respects_block_and_session_retention() -> None:
    now = datetime(2026, 9, 22, 5, 0, tzinfo=UTC)
    suffix = uuid4().hex[:8]
    bucket_keys = [f"cleanup-{suffix}-{index}" for index in range(4)]
    session_ids: list[int] = []

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "codex-test-viewer"))
        assert user is not None

        db.add_all(
            [
                AuthRateLimitBucket(
                    bucket_type="LOGIN_IP",
                    bucket_key_hash=bucket_keys[0],
                    failure_count=1,
                    window_started_at=now - timedelta(days=3),
                    blocked_until=None,
                    updated_at=now - timedelta(hours=25),
                ),
                AuthRateLimitBucket(
                    bucket_type="LOGIN_IP",
                    bucket_key_hash=bucket_keys[1],
                    failure_count=5,
                    window_started_at=now - timedelta(days=3),
                    blocked_until=now + timedelta(minutes=10),
                    updated_at=now - timedelta(hours=25),
                ),
                AuthRateLimitBucket(
                    bucket_type="LOGIN_IP",
                    bucket_key_hash=bucket_keys[2],
                    failure_count=1,
                    window_started_at=now - timedelta(hours=1),
                    blocked_until=None,
                    updated_at=now - timedelta(hours=1),
                ),
                AuthRateLimitBucket(
                    bucket_type="LOGIN_IP",
                    bucket_key_hash=bucket_keys[3],
                    failure_count=5,
                    window_started_at=now - timedelta(days=3),
                    blocked_until=now - timedelta(hours=1),
                    updated_at=now - timedelta(hours=25),
                ),
            ]
        )

        sessions = [
            UserSession(
                user_id=user.id,
                refresh_token_hash=f"{index:064x}",
                created_at=now - timedelta(days=200),
                expires_at=now - timedelta(days=100),
                revoked_at=None,
            )
            for index in range(1, 3)
        ]
        sessions[1].expires_at = now - timedelta(days=10)
        revoked_old = UserSession(
            user_id=user.id,
            refresh_token_hash=f"{3:064x}",
            created_at=now - timedelta(days=200),
            expires_at=now + timedelta(days=10),
            revoked_at=now - timedelta(days=100),
            revoke_reason="LOGOUT",
        )
        revoked_recent = UserSession(
            user_id=user.id,
            refresh_token_hash=f"{4:064x}",
            created_at=now - timedelta(days=20),
            expires_at=now + timedelta(days=10),
            revoked_at=now - timedelta(days=10),
            revoke_reason="LOGOUT",
        )
        active = UserSession(
            user_id=user.id,
            refresh_token_hash=f"{5:064x}",
            created_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=29),
        )
        db.add_all([*sessions, revoked_old, revoked_recent, active])
        await db.commit()
        for row in [*sessions, revoked_old, revoked_recent, active]:
            await db.refresh(row)
            session_ids.append(row.id)

    try:
        await cleanup_auth_state(now=now)

        async with AsyncSessionLocal() as db:
            remaining_buckets = {
                row.bucket_key_hash
                for row in (
                    await db.scalars(
                        select(AuthRateLimitBucket).where(
                            AuthRateLimitBucket.bucket_key_hash.in_(bucket_keys)
                        )
                    )
                ).all()
            }
            remaining_sessions = set(
                (
                    await db.scalars(
                        select(UserSession.id).where(UserSession.id.in_(session_ids))
                    )
                ).all()
            )

        assert bucket_keys[0] not in remaining_buckets
        assert bucket_keys[3] not in remaining_buckets
        assert bucket_keys[1] in remaining_buckets
        assert bucket_keys[2] in remaining_buckets

        assert session_ids[0] not in remaining_sessions
        assert session_ids[2] not in remaining_sessions
        assert session_ids[1] in remaining_sessions
        assert session_ids[3] in remaining_sessions
        assert session_ids[4] in remaining_sessions
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(AuthRateLimitBucket).where(
                    AuthRateLimitBucket.bucket_key_hash.in_(bucket_keys)
                )
            )
            await db.execute(delete(UserSession).where(UserSession.id.in_(session_ids)))
            await db.commit()
