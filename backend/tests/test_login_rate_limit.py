from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.client_ip import resolve_request_client_ip
from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.db.session import AsyncSessionLocal
from app.models.auth_session import AuthRateLimitBucket
from app.services.login_rate_limit_service import (
    precheck_login_rate_limit,
    record_login_failure,
    record_login_success,
)


def _request(client_host: str, forwarded_for: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers,
            "client": (client_host, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


@pytest.fixture(autouse=True)
async def clear_rate_limit_buckets():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuthRateLimitBucket))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuthRateLimitBucket))
        await db.commit()


@pytest.mark.asyncio
async def test_identity_bucket_blocks_and_exposes_retry_after(monkeypatch) -> None:
    monkeypatch.setattr(settings, "login_rate_limit_identity_attempts", 2)
    monkeypatch.setattr(settings, "login_rate_limit_ip_attempts", 100)
    monkeypatch.setattr(settings, "login_rate_limit_block_seconds", 900)
    now = datetime(2026, 9, 22, 4, 0, tzinfo=UTC)

    async with AsyncSessionLocal() as db:
        await record_login_failure(db, "Alice", "203.0.113.10", now=now)
        with pytest.raises(ApplicationError) as caught:
            await record_login_failure(db, "alice", "203.0.113.10", now=now)

    assert caught.value.code == "LOGIN_RATE_LIMITED"
    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "900"}


@pytest.mark.asyncio
async def test_ip_bucket_blocks_username_spraying(monkeypatch) -> None:
    monkeypatch.setattr(settings, "login_rate_limit_identity_attempts", 100)
    monkeypatch.setattr(settings, "login_rate_limit_ip_attempts", 3)
    now = datetime(2026, 9, 22, 4, 5, tzinfo=UTC)

    async with AsyncSessionLocal() as db:
        await record_login_failure(db, "alice", "198.51.100.20", now=now)
        await record_login_failure(db, "bob", "198.51.100.20", now=now)
        with pytest.raises(ApplicationError) as caught:
            await record_login_failure(db, "charlie", "198.51.100.20", now=now)

    assert caught.value.code == "LOGIN_RATE_LIMITED"


@pytest.mark.asyncio
async def test_success_clears_identity_bucket_but_keeps_ip_history(monkeypatch) -> None:
    monkeypatch.setattr(settings, "login_rate_limit_identity_attempts", 5)
    monkeypatch.setattr(settings, "login_rate_limit_ip_attempts", 30)
    now = datetime(2026, 9, 22, 4, 10, tzinfo=UTC)

    async with AsyncSessionLocal() as db:
        await record_login_failure(db, "alice", "203.0.113.30", now=now)
        await record_login_success(db, "alice", "203.0.113.30")
        rows = (await db.scalars(select(AuthRateLimitBucket))).all()

    identity_rows = [row for row in rows if row.bucket_type == "LOGIN_IDENTITY_IP"]
    ip_rows = [row for row in rows if row.bucket_type == "LOGIN_IP"]
    assert identity_rows == []
    assert len(ip_rows) == 1
    assert ip_rows[0].failure_count == 1


@pytest.mark.asyncio
async def test_bucket_keys_do_not_store_raw_username_or_ip() -> None:
    now = datetime(2026, 9, 22, 4, 15, tzinfo=UTC)
    username = "secret-user"
    client_ip = "203.0.113.44"

    async with AsyncSessionLocal() as db:
        await record_login_failure(db, username, client_ip, now=now)
        rows = (await db.scalars(select(AuthRateLimitBucket))).all()

    assert rows
    assert all(username not in row.bucket_key_hash for row in rows)
    assert all(client_ip not in row.bucket_key_hash for row in rows)
    assert all(len(row.bucket_key_hash) == 64 for row in rows)


@pytest.mark.asyncio
async def test_precheck_rejects_existing_block(monkeypatch) -> None:
    monkeypatch.setattr(settings, "login_rate_limit_identity_attempts", 1)
    monkeypatch.setattr(settings, "login_rate_limit_ip_attempts", 100)
    now = datetime(2026, 9, 22, 4, 20, tzinfo=UTC)

    async with AsyncSessionLocal() as db:
        with pytest.raises(ApplicationError):
            await record_login_failure(db, "alice", "192.0.2.5", now=now)
        with pytest.raises(ApplicationError) as caught:
            await precheck_login_rate_limit(
                db,
                "alice",
                "192.0.2.5",
                now=now,
            )

    assert caught.value.code == "LOGIN_RATE_LIMITED"
    assert caught.value.headers["Retry-After"] == "900"


def test_untrusted_forwarded_for_is_ignored(monkeypatch) -> None:
    monkeypatch.setattr(settings, "login_rate_limit_trusted_proxy_cidrs", [])
    request = _request("10.1.2.3", "198.51.100.99")

    assert resolve_request_client_ip(request) == "10.1.2.3"


def test_trusted_proxy_uses_leftmost_valid_forwarded_client(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "login_rate_limit_trusted_proxy_cidrs",
        ["10.0.0.0/8"],
    )
    request = _request("10.1.2.3", "198.51.100.99, 10.1.2.3")

    assert resolve_request_client_ip(request) == "198.51.100.99"
