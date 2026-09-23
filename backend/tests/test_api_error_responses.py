from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.enums import UserRole
from tests.session_auth import session_headers
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.project import Project
from app.models.scenario_catalog import ScenarioCatalog
from app.models.user import User


async def _headers_for_username(username: str) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))
        assert user is not None
        return await session_headers(user)


async def _admin_headers() -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(
            select(User).where(
                User.system_role == UserRole.ADMIN,
                User.is_deleted.is_(False),
            )
        )
        assert user is not None
        return await session_headers(user)


@pytest.mark.asyncio
async def test_unknown_system_is_canonical_404() -> None:
    response = TestClient(app).get(
        f"/api/v1/aquaponics-systems/{uuid4()}",
        headers=await _headers_for_username("codex-test-owner"),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "AQUAPONICS_SYSTEM_NOT_FOUND"
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_cross_project_resource_is_caller_safe_404() -> None:
    async with AsyncSessionLocal() as db:
        system = await db.scalar(
            select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
        )
        assert system is not None
        system_id = system.public_id
        private_name = system.name

    response = TestClient(app).get(
        f"/api/v1/aquaponics-systems/{system_id}",
        headers=await _headers_for_username("codex-test-viewer"),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "AQUAPONICS_SYSTEM_NOT_FOUND"
    assert private_name not in response.text


@pytest.mark.asyncio
async def test_duplicate_scenario_catalog_is_canonical_409() -> None:
    async with AsyncSessionLocal() as db:
        catalog = await db.scalar(
            select(ScenarioCatalog).where(ScenarioCatalog.is_deleted.is_(False))
        )
        assert catalog is not None
        payload = {
            "device_template_id": catalog.device_template_id,
            "code": catalog.code,
            "name": "Duplicate catalog contract test",
        }

    response = TestClient(app).post(
        "/api/v1/scenario-catalogs",
        json=payload,
        headers=await _admin_headers(),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SCENARIO_CATALOG_CODE_EXISTS"
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_invalid_create_system_payload_is_canonical_422() -> None:
    response = TestClient(app).post(
        "/api/v1/aquaponics-systems",
        json={
            "owner_user_id": "not-a-uuid",
            "device_template_id": 0,
            "scenario_catalog_id": 0,
        },
        headers=await _admin_headers(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert isinstance(response.json()["detail"], str)
    assert "input" not in response.text


@pytest.mark.asyncio
async def test_mqtt_export_invalid_public_host_is_canonical_500(
    monkeypatch,
) -> None:
    async with AsyncSessionLocal() as db:
        system = await db.scalar(
            select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
        )
        assert system is not None
        system_id = system.public_id

    monkeypatch.setattr(settings, "mqtt_public_host", "127.0.0.1")
    response = TestClient(app, raise_server_exceptions=False).get(
        f"/api/v1/aquaponics-systems/{system_id}/mqtt-config/export",
        headers=await _admin_headers(),
    )
    assert response.status_code == 500
    assert response.json()["code"] == "MQTT_PUBLIC_HOST_INVALID"
    assert response.json()["detail"] == (
        "MQTT_PUBLIC_HOST phải là địa chỉ mà thiết bị trong mạng LAN truy cập được."
    )
