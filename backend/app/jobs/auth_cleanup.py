from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.auth_session import AuthRateLimitBucket, UserSession


_CLEANUP_BATCH_SIZE = 500


async def cleanup_auth_state(*, now: datetime | None = None) -> None:
    timestamp = now or datetime.now(UTC)
    bucket_cutoff = timestamp - timedelta(
        hours=settings.auth_rate_limit_retention_hours
    )
    session_cutoff = timestamp - timedelta(
        days=settings.auth_session_retention_days
    )

    async with AsyncSessionLocal() as db:
        bucket_ids = list(
            (
                await db.scalars(
                    select(AuthRateLimitBucket.id)
                    .where(
                        AuthRateLimitBucket.updated_at < bucket_cutoff,
                        or_(
                            AuthRateLimitBucket.blocked_until.is_(None),
                            AuthRateLimitBucket.blocked_until <= timestamp,
                        ),
                    )
                    .order_by(AuthRateLimitBucket.updated_at, AuthRateLimitBucket.id)
                    .limit(_CLEANUP_BATCH_SIZE)
                )
            ).all()
        )
        if bucket_ids:
            await db.execute(
                delete(AuthRateLimitBucket).where(
                    AuthRateLimitBucket.id.in_(bucket_ids)
                )
            )

        session_ids = list(
            (
                await db.scalars(
                    select(UserSession.id)
                    .where(
                        or_(
                            (
                                UserSession.revoked_at.is_not(None)
                                & (UserSession.revoked_at < session_cutoff)
                            ),
                            (
                                UserSession.revoked_at.is_(None)
                                & (UserSession.expires_at < session_cutoff)
                            ),
                        )
                    )
                    .order_by(UserSession.id)
                    .limit(_CLEANUP_BATCH_SIZE)
                )
            ).all()
        )
        if session_ids:
            await db.execute(
                delete(UserSession).where(UserSession.id.in_(session_ids))
            )

        if bucket_ids or session_ids:
            await db.commit()
