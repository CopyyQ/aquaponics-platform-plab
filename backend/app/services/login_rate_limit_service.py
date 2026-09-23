from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.models.auth_session import AuthRateLimitBucket


IDENTITY_IP_BUCKET = "LOGIN_IDENTITY_IP"
IP_BUCKET = "LOGIN_IP"


def _normalize_username(username: str) -> str:
    return username.strip().casefold()


def _bucket_hash(kind: str, material: str) -> str:
    message = f"login-rate:{kind}:{material}".encode()
    return hmac.new(
        settings.secret_key.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()


def _identity_bucket_key(username: str, client_ip: str) -> str:
    return _bucket_hash(
        IDENTITY_IP_BUCKET,
        f"{_normalize_username(username)}\x1f{client_ip}",
    )


def _ip_bucket_key(client_ip: str) -> str:
    return _bucket_hash(IP_BUCKET, client_ip)


def resolve_client_ip(peer: str, forwarded_for: str | None = None) -> str:
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer

    trusted = False
    for raw_cidr in settings.login_rate_limit_trusted_proxy_cidrs:
        try:
            if peer_address in ipaddress.ip_network(raw_cidr, strict=False):
                trusted = True
                break
        except ValueError:
            continue

    if not trusted or not forwarded_for:
        return peer

    candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return peer


def _retry_after_seconds(blocked_until: datetime, now: datetime) -> int:
    return max(1, math.ceil((blocked_until - now).total_seconds()))


def _rate_limited_error(retry_after_seconds: int) -> ApplicationError:
    return ApplicationError(
        "LOGIN_RATE_LIMITED",
        "Thử đăng nhập quá nhiều lần. Vui lòng thử lại sau.",
        429,
        headers={"Retry-After": str(max(1, retry_after_seconds))},
    )


def _bucket_specs(username: str, client_ip: str) -> tuple[tuple[str, str, int], ...]:
    return (
        (
            IDENTITY_IP_BUCKET,
            _identity_bucket_key(username, client_ip),
            settings.login_rate_limit_identity_attempts,
        ),
        (
            IP_BUCKET,
            _ip_bucket_key(client_ip),
            settings.login_rate_limit_ip_attempts,
        ),
    )


async def precheck_login_rate_limit(
    db: AsyncSession,
    username: str,
    client_ip: str,
    *,
    now: datetime | None = None,
) -> None:
    timestamp = now or datetime.now(UTC)
    for bucket_type, bucket_key_hash, _threshold in _bucket_specs(
        username,
        client_ip,
    ):
        row = await db.scalar(
            select(AuthRateLimitBucket).where(
                AuthRateLimitBucket.bucket_type == bucket_type,
                AuthRateLimitBucket.bucket_key_hash == bucket_key_hash,
            )
        )
        if row is not None and row.blocked_until is not None and row.blocked_until > timestamp:
            raise _rate_limited_error(
                _retry_after_seconds(row.blocked_until, timestamp)
            )


async def _locked_bucket(
    db: AsyncSession,
    *,
    bucket_type: str,
    bucket_key_hash: str,
    now: datetime,
) -> AuthRateLimitBucket:
    await db.execute(
        pg_insert(AuthRateLimitBucket)
        .values(
            bucket_type=bucket_type,
            bucket_key_hash=bucket_key_hash,
            failure_count=0,
            window_started_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=[
                AuthRateLimitBucket.bucket_type,
                AuthRateLimitBucket.bucket_key_hash,
            ]
        )
    )
    row = await db.scalar(
        select(AuthRateLimitBucket)
        .where(
            AuthRateLimitBucket.bucket_type == bucket_type,
            AuthRateLimitBucket.bucket_key_hash == bucket_key_hash,
        )
        .with_for_update()
    )
    if row is None:
        raise RuntimeError("Login rate-limit bucket disappeared after upsert")
    return row


async def record_login_failure(
    db: AsyncSession,
    username: str,
    client_ip: str,
    *,
    now: datetime | None = None,
) -> None:
    timestamp = now or datetime.now(UTC)
    window = timedelta(seconds=settings.login_rate_limit_window_seconds)
    block = timedelta(seconds=settings.login_rate_limit_block_seconds)
    retry_after: int | None = None

    for bucket_type, bucket_key_hash, threshold in _bucket_specs(
        username,
        client_ip,
    ):
        row = await _locked_bucket(
            db,
            bucket_type=bucket_type,
            bucket_key_hash=bucket_key_hash,
            now=timestamp,
        )

        if row.blocked_until is not None and row.blocked_until > timestamp:
            remaining = _retry_after_seconds(row.blocked_until, timestamp)
            retry_after = max(retry_after or 0, remaining)
            continue

        if row.window_started_at + window <= timestamp:
            row.failure_count = 0
            row.window_started_at = timestamp
            row.blocked_until = None

        row.failure_count += 1
        row.updated_at = timestamp
        if row.failure_count >= threshold:
            row.blocked_until = timestamp + block
            retry_after = max(
                retry_after or 0,
                _retry_after_seconds(row.blocked_until, timestamp),
            )

    await db.commit()
    if retry_after is not None:
        raise _rate_limited_error(retry_after)


async def record_login_success(
    db: AsyncSession,
    username: str,
    client_ip: str,
) -> None:
    await db.execute(
        delete(AuthRateLimitBucket).where(
            AuthRateLimitBucket.bucket_type == IDENTITY_IP_BUCKET,
            AuthRateLimitBucket.bucket_key_hash
            == _identity_bucket_key(username, client_ip),
        )
    )
    await db.commit()
