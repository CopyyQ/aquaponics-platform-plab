from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.enums import UserRole, UserStatus
from app.core.security import hash_password
from tests.session_auth import session_headers
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.device_template import DeviceTemplate
from app.models.permission import Role
from app.models.scenario_catalog import ScenarioCatalog
from app.models.user import User
from app.schemas.scenario_catalog import ScenarioCatalogCreate, ScenarioCatalogRead
from scripts.seed import CANONICAL_DEVICE_TEMPLATE_CODE, CANONICAL_SCENARIO_CATALOG_CODE


def test_scenario_catalog_requires_device_template() -> None:
    assert "device_template_id" in ScenarioCatalog.__table__.c
    column = ScenarioCatalog.__table__.c.device_template_id
    assert column.nullable is False
    assert ScenarioCatalogCreate.model_fields["device_template_id"].is_required()
    assert "device_template_id" in ScenarioCatalogRead.model_fields
    assert "resource_code" in ScenarioCatalogRead.model_fields["items"].annotation.__args__[0].model_fields


@pytest.mark.asyncio
async def test_scenario_catalog_is_scoped_to_device_resources() -> None:
    suffix = uuid4().hex[:10].upper()
    code = f"DEVICE_SCENARIO_{suffix}"
    created_id: int | None = None

    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        template = await db.scalar(
            select(DeviceTemplate)
            .options(
                selectinload(DeviceTemplate.sensor_mappings),
                selectinload(DeviceTemplate.actuator_mappings),
            )
            .where(DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE)
        )
        assert admin is not None and template is not None
        template_id = template.id
        expected_sensor_models = {
            mapping.sensor_model_id for mapping in template.sensor_mappings
        }
        expected_actuator_models = {
            mapping.actuator_model_id for mapping in template.actuator_mappings
        }
        expected_sensor_codes = {mapping.code for mapping in template.sensor_mappings}
        expected_actuator_codes = {mapping.code for mapping in template.actuator_mappings}
        auth = await session_headers(admin)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/v1/scenario-catalogs",
                headers=auth,
                json={
                    "device_template_id": template_id,
                    "code": code,
                    "name": f"Kịch bản {suffix}",
                    "description": "Kiểm thử quan hệ thiết bị - kịch bản",
                },
            )
            assert created.status_code == 201, created.text
            payload = created.json()
            created_id = payload["id"]
            assert payload["device_template_id"] == template_id
            assert {
                item["sensor_model_id"]
                for item in payload["items"]
                if item["target_type"] == "SENSOR"
            } == expected_sensor_models
            assert {
                item["actuator_model_id"]
                for item in payload["items"]
                if item["target_type"] == "ACTUATOR"
            } == expected_actuator_models
            assert {
                item["resource_code"]
                for item in payload["items"]
                if item["target_type"] == "SENSOR"
            } == expected_sensor_codes
            assert {
                item["resource_code"]
                for item in payload["items"]
                if item["target_type"] == "ACTUATOR"
            } == expected_actuator_codes

            scoped = await client.get(
                "/api/v1/scenario-catalogs",
                params={"device_template_id": template_id},
                headers=auth,
            )
            assert scoped.status_code == 200, scoped.text
            assert created_id in {item["id"] for item in scoped.json()}
            assert all(
                item["device_template_id"] == template_id for item in scoped.json()
            )
    finally:
        if created_id is not None:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(ScenarioCatalog).where(ScenarioCatalog.id == created_id)
                )
                await db.commit()


@pytest.mark.asyncio
async def test_project_creation_rejects_scenario_from_another_device() -> None:
    suffix = uuid4().hex[:10]
    user_id: int | None = None
    other_template_id: int | None = None

    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        viewer_role = await db.scalar(select(Role).where(Role.code == "VIEWER"))
        canonical_scenario = await db.scalar(
            select(ScenarioCatalog).where(
                ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE
            )
        )
        assert admin is not None and viewer_role is not None and canonical_scenario is not None

        other_template = DeviceTemplate(
            code=f"OTHER_DEVICE_{suffix.upper()}",
            name="Thiết bị không thuộc kịch bản",
            description="Dùng để kiểm thử mismatch",
            is_active=True,
        )
        owner = User(
            username=f"scenario-owner-{suffix}",
            password_hash=hash_password("TestPassword@123"),
            full_name="Scenario mismatch owner",
            email=f"scenario-owner-{suffix}@example.test",
            phone_number=f"06{suffix[:8]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add_all([other_template, owner])
        await db.commit()
        await db.refresh(other_template)
        await db.refresh(owner)
        other_template_id = other_template.id
        user_id = owner.id
        owner_public_id = str(owner.public_id)
        scenario_id = canonical_scenario.id
        auth = await session_headers(admin)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/users/{owner_public_id}/aquaponics-systems",
                headers=auth,
                json={
                    "device_template_id": other_template_id,
                    "scenario_catalog_id": scenario_id,
                },
            )
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "SCENARIO_CATALOG_DEVICE_MISMATCH"
    finally:
        async with AsyncSessionLocal() as db:
            if user_id is not None:
                await db.execute(delete(User).where(User.id == user_id))
            if other_template_id is not None:
                await db.execute(
                    delete(DeviceTemplate).where(DeviceTemplate.id == other_template_id)
                )
            await db.commit()
