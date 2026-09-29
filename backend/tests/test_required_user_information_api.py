from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.enums import UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.permission import Role
from app.models.user import User
from tests.session_auth import session_headers


def _digits() -> str:
    return str(uuid4().int)[-9:]


async def _admin_and_viewer_role() -> tuple[User, Role]:
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        viewer_role = await db.scalar(select(Role).where(Role.code == "VIEWER"))
        assert admin is not None
        assert viewer_role is not None
        return admin, viewer_role


async def _legacy_user(*, address: str, prefix: str) -> User:
    digits = _digits()
    async with AsyncSessionLocal() as db:
        viewer_role = await db.scalar(select(Role).where(Role.code == "VIEWER"))
        assert viewer_role is not None
        row = User(
            username=f"{prefix}-{uuid4().hex[:10]}",
            password_hash=hash_password("RequiredInfo@123"),
            full_name="Người dùng kiểm thử",
            email=f"{prefix}-{uuid4().hex[:10]}@example.com",
            phone_number=f"0{digits}",
            address=address,
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


@pytest.mark.asyncio
async def test_create_user_requires_address() -> None:
    admin, viewer_role = await _admin_and_viewer_role()
    headers = await session_headers(admin)
    digits = _digits()
    payload = {
        "username": f"required-address-{uuid4().hex[:8]}",
        "full_name": "Người dùng đầy đủ",
        "email": f"required-address-{uuid4().hex[:8]}@example.com",
        "phone_number": f"0{digits}",
        "role_id": viewer_role.id,
        "password": "RequiredInfo@123",
        "confirm_password": "RequiredInfo@123",
        "must_change_password": True,
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/users", headers=headers, json=payload)

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("full_name", "   "),
        ("phone_number", "   "),
        ("address", "   "),
    ],
)
async def test_create_user_rejects_blank_required_profile_fields(
    field: str,
    value: str,
) -> None:
    admin, viewer_role = await _admin_and_viewer_role()
    headers = await session_headers(admin)
    digits = _digits()
    payload = {
        "username": f"blank-profile-{uuid4().hex[:8]}",
        "full_name": "Người dùng đầy đủ",
        "email": f"blank-profile-{uuid4().hex[:8]}@example.com",
        "phone_number": f"0{digits}",
        "address": "Hà Nội",
        "role_id": viewer_role.id,
        "password": "RequiredInfo@123",
        "confirm_password": "RequiredInfo@123",
        "must_change_password": True,
    }
    payload[field] = value

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/users", headers=headers, json=payload)

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["   ", None])
async def test_admin_update_rejects_invalid_required_field(address: str | None) -> None:
    admin, _ = await _admin_and_viewer_role()
    target = await _legacy_user(address="Hà Nội", prefix="admin-invalid")
    headers = await session_headers(admin)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.patch(
            f"/api/v1/users/{target.public_id}",
            headers=headers,
            json={"address": address},
        )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_admin_update_requires_legacy_incomplete_user_to_be_completed() -> None:
    admin, _ = await _admin_and_viewer_role()
    target = await _legacy_user(address="", prefix="admin-legacy")
    headers = await session_headers(admin)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        incomplete = await client.patch(
            f"/api/v1/users/{target.public_id}",
            headers=headers,
            json={"full_name": "Tên mới"},
        )
        completed = await client.patch(
            f"/api/v1/users/{target.public_id}",
            headers=headers,
            json={"address": "  Hà Nội  "},
        )

    assert incomplete.status_code == 422, incomplete.text
    assert completed.status_code == 200, completed.text
    assert completed.json()["address"] == "Hà Nội"


@pytest.mark.asyncio
async def test_self_update_requires_legacy_incomplete_user_to_be_completed() -> None:
    target = await _legacy_user(address="", prefix="self-legacy")
    headers = await session_headers(target)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        incomplete = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"full_name": "Tên mới"},
        )
        completed = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"address": "  Hà Nội  "},
        )

    assert incomplete.status_code == 422, incomplete.text
    assert completed.status_code == 200, completed.text
    assert completed.json()["address"] == "Hà Nội"


@pytest.mark.asyncio
async def test_self_update_keeps_partial_updates_for_complete_profile() -> None:
    target = await _legacy_user(address="Hà Nội", prefix="self-complete")
    headers = await session_headers(target)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"full_name": "  Tên hoàn chỉnh  "},
        )

    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "Tên hoàn chỉnh"
    assert response.json()["address"] == "Hà Nội"
