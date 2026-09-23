from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.enums import UserRole, UserStatus
from app.core.security import decode_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.auth_session import AuthRateLimitBucket, UserSession
from app.models.audit_log import AuditLog
from app.models.permission import Role
from app.models.user import User


@pytest_asyncio.fixture
async def auth_user():
    suffix = uuid4().hex[:10]
    username = f"session-user-{suffix}"
    password = "SessionPassword@123"
    async with AsyncSessionLocal() as db:
        role = await db.scalar(select(Role).where(Role.code == "VIEWER"))
        assert role is not None
        user = User(
            username=username,
            password_hash=hash_password(password),
            full_name="Session API regression",
            email=f"{username}@example.com",
            phone_number=f"091{suffix[:7]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    yield username, password, user_id

    async with AsyncSessionLocal() as db:
        await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
        await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.execute(delete(AuthRateLimitBucket))
        await db.commit()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_login_creates_server_session_cookie_and_sid(auth_user) -> None:
    username, password, user_id = auth_user
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )

    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert UUID(payload["sid"])
    set_cookie = response.headers["set-cookie"]
    assert settings.refresh_cookie_name in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    async with AsyncSessionLocal() as db:
        session = await db.scalar(
            select(UserSession).where(UserSession.public_id == UUID(payload["sid"]))
        )
        assert session is not None
        assert session.revoked_at is None
        assert session.expires_at - session.created_at == timedelta(days=30)


@pytest.mark.asyncio
async def test_refresh_rotates_cookie_and_access_token(auth_user) -> None:
    username, password, _user_id = auth_user
    async with _client() as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200
        old_cookie = client.cookies.get(settings.refresh_cookie_name)
        old_access = login.json()["access_token"]

        refreshed = await client.post("/api/v1/auth/refresh")
        new_cookie = client.cookies.get(settings.refresh_cookie_name)

    assert refreshed.status_code == 200
    assert new_cookie and old_cookie and new_cookie != old_cookie
    assert refreshed.json()["access_token"] != old_access
    assert decode_access_token(refreshed.json()["access_token"])["sid"] == decode_access_token(old_access)["sid"]


@pytest.mark.asyncio
async def test_reusing_rotated_refresh_cookie_revokes_session(auth_user) -> None:
    username, password, _user_id = auth_user
    async with _client() as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        old_cookie = client.cookies.get(settings.refresh_cookie_name)
        sid = UUID(decode_access_token(login.json()["access_token"])["sid"])
        refreshed = await client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200

    async with _client() as replay_client:
        replay_client.cookies.set(settings.refresh_cookie_name, old_cookie or "")
        replay = await replay_client.post("/api/v1/auth/refresh")

    assert replay.status_code == 401
    async with AsyncSessionLocal() as db:
        session = await db.scalar(select(UserSession).where(UserSession.public_id == sid))
        assert session is not None
        assert session.revoked_at is not None
        assert session.revoke_reason == "REFRESH_TOKEN_REPLAY"


@pytest.mark.asyncio
async def test_refresh_rejects_absolute_30_day_expiry(auth_user) -> None:
    username, password, _user_id = auth_user
    async with _client() as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        sid = UUID(decode_access_token(login.json()["access_token"])["sid"])
        async with AsyncSessionLocal() as db:
            session = await db.scalar(select(UserSession).where(UserSession.public_id == sid))
            assert session is not None
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()

        refreshed = await client.post("/api/v1/auth/refresh")

    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session_and_invalidates_existing_access_token(auth_user) -> None:
    username, password, _user_id = auth_user
    async with _client() as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        access_token = login.json()["access_token"]
        sid = UUID(decode_access_token(access_token)["sid"])

        logout = await client.post("/api/v1/auth/logout")
        after_logout = await client.get(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert logout.status_code == 200
    assert after_logout.status_code == 401
    async with AsyncSessionLocal() as db:
        session = await db.scalar(select(UserSession).where(UserSession.public_id == sid))
        assert session is not None
        assert session.revoked_at is not None


@pytest.mark.asyncio
async def test_login_rate_limit_returns_retry_after(auth_user, monkeypatch) -> None:
    username, _password, _user_id = auth_user
    monkeypatch.setattr(settings, "login_rate_limit_identity_attempts", 1)
    monkeypatch.setattr(settings, "login_rate_limit_ip_attempts", 100)

    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "WrongPassword@123"},
        )

    assert response.status_code == 429
    assert response.json()["code"] == "LOGIN_RATE_LIMITED"
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_unapproved_origin_is_rejected_before_login_state_mutation(auth_user) -> None:
    username, password, user_id = auth_user
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"username": username, "password": password},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_ORIGIN_REJECTED"
    async with AsyncSessionLocal() as db:
        sessions = (
            await db.scalars(select(UserSession).where(UserSession.user_id == user_id))
        ).all()
        assert sessions == []


def test_auth_openapi_documents_session_and_rate_limit_errors() -> None:
    schema = app.openapi()

    login_responses = schema["paths"]["/api/v1/auth/login"]["post"]["responses"]
    refresh_responses = schema["paths"]["/api/v1/auth/refresh"]["post"]["responses"]
    logout_responses = schema["paths"]["/api/v1/auth/logout"]["post"]["responses"]

    assert {"403", "429"} <= set(login_responses)
    assert {"401", "403"} <= set(refresh_responses)
    assert {"401", "403"} <= set(logout_responses)
    for responses in (login_responses, refresh_responses, logout_responses):
        for status_code in set(responses) & {"401", "403", "429"}:
            schema_ref = responses[status_code]["content"]["application/json"]["schema"]["$ref"]
            assert schema_ref == "#/components/schemas/ApiErrorResponse"
