import re
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.enums import UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.device_template import DeviceTemplate
from app.models.operational_alert import AlertRule, AlertRuleProjectOverride
from app.models.permission import Role
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.scenario_catalog import ScenarioCatalog
from app.models.sensor import Sensor
from app.models.user import User
from scripts.seed import CANONICAL_DEVICE_TEMPLATE_CODE, CANONICAL_SCENARIO_CATALOG_CODE
from tests.session_auth import session_headers


async def _cleanup_systems(public_ids: list[str]) -> None:
    if not public_ids:
        return
    async with AsyncSessionLocal() as db:
        project_ids = list(
            (
                await db.scalars(
                    select(Project.id).where(Project.public_id.in_(public_ids))
                )
            ).all()
        )
        if not project_ids:
            return
        rule_ids = list(
            (
                await db.scalars(
                    select(AlertRuleProjectOverride.rule_id).where(
                        AlertRuleProjectOverride.project_id.in_(project_ids)
                    )
                )
            ).all()
        )
        if rule_ids:
            await db.execute(delete(AlertRule).where(AlertRule.id.in_(rule_ids)))
        scenario_ids = select(ProjectScenario.id).where(
            ProjectScenario.project_id.in_(project_ids)
        )
        scenario_item_ids = select(ProjectScenarioItem.id).where(
            ProjectScenarioItem.project_scenario_id.in_(scenario_ids)
        )
        await db.execute(
            delete(ProjectScenarioBranch).where(
                ProjectScenarioBranch.project_scenario_item_id.in_(scenario_item_ids)
            )
        )
        await db.execute(
            delete(ProjectScenarioItem).where(
                ProjectScenarioItem.project_scenario_id.in_(scenario_ids)
            )
        )
        await db.execute(
            delete(ProjectScenario).where(ProjectScenario.id.in_(scenario_ids))
        )
        device_ids = select(Device.id).where(Device.project_id.in_(project_ids))
        await db.execute(delete(Sensor).where(Sensor.device_id.in_(device_ids)))
        await db.execute(delete(Actuator).where(Actuator.device_id.in_(device_ids)))
        await db.execute(delete(Device).where(Device.project_id.in_(project_ids)))
        await db.execute(delete(ProjectMember).where(ProjectMember.project_id.in_(project_ids)))
        await db.execute(delete(Project).where(Project.id.in_(project_ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_create_aquaponics_system_uses_catalogs_fixed_name_and_one_owner_limit() -> None:
    suffix = uuid4().hex[:10]
    user_ids: list[int] = []
    system_ids: list[str] = []

    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        viewer_role = await db.scalar(select(Role).where(Role.code == "VIEWER"))
        template = await db.scalar(
            select(DeviceTemplate).where(
                DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE
            )
        )
        scenario = await db.scalar(
            select(ScenarioCatalog).where(
                ScenarioCatalog.code == CANONICAL_SCENARIO_CATALOG_CODE
            )
        )
        assert admin and viewer_role and template and scenario

        active = User(
            username=f"owner-{suffix}",
            password_hash=hash_password("TestPassword@123"),
            full_name="Active owner",
            email=f"owner-{suffix}@example.test",
            phone_number=f"08{suffix[:8]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        global_owner = User(
            username=f"global-owner-{suffix}",
            password_hash=hash_password("TestPassword@123"),
            full_name="Global owner",
            email=f"global-owner-{suffix}@example.test",
            phone_number=f"09{suffix[:8]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        inactive = User(
            username=f"inactive-{suffix}",
            password_hash=hash_password("TestPassword@123"),
            full_name="Inactive owner",
            email=f"inactive-{suffix}@example.test",
            phone_number=f"07{suffix[:8]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.DISABLED,
            must_change_password=False,
        )
        db.add_all([active, global_owner, inactive])
        await db.commit()
        for row in (active, global_owner, inactive):
            await db.refresh(row)
            user_ids.append(row.id)

        headers = await session_headers(admin)
        active_id = str(active.public_id)
        global_owner_id = str(global_owner.public_id)
        inactive_id = str(inactive.public_id)
        admin_id = str(admin.public_id)
        catalog_payload = {
            "device_template_id": template.id,
            "scenario_catalog_id": scenario.id,
        }

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post(
                f"/api/v1/users/{active_id}/aquaponics-systems",
                headers=headers,
                json=catalog_payload,
            )
            assert first.status_code == 201, first.text
            created = first.json()
            system_ids.append(created["id"])
            assert created["name"] == "Hệ thống Aquaponics"
            assert created["owner_user_id"] == active_id
            assert created["device_template_id"] == template.id
            assert created["scenario_catalog_id"] == scenario.id
            assert re.fullmatch(r"AQS-[A-Z0-9_-]{12}", created["code"])

            second = await client.post(
                f"/api/v1/users/{active_id}/aquaponics-systems",
                headers=headers,
                json=catalog_payload,
            )
            assert second.status_code == 409, second.text
            assert second.json()["code"] == "OWNER_ALREADY_HAS_AQUAPONICS_SYSTEM"

            owned = await client.get(
                f"/api/v1/users/{active_id}/aquaponics-systems", headers=headers
            )
            assert owned.status_code == 200
            assert [item["id"] for item in owned.json()] == [created["id"]]
            assert owned.json()[0]["relationship"] == "OWNER"

            extra_fields = await client.post(
                f"/api/v1/users/{global_owner_id}/aquaponics-systems",
                headers=headers,
                json={**catalog_payload, "name": "Không được phép", "code": "CLIENT-CODE"},
            )
            assert extra_fields.status_code == 422

            inactive_path = await client.post(
                f"/api/v1/users/{inactive_id}/aquaponics-systems",
                headers=headers,
                json=catalog_payload,
            )
            assert inactive_path.status_code == 422

            missing_user = await client.post(
                "/api/v1/aquaponics-systems",
                headers=headers,
                json={**catalog_payload, "owner_user_id": str(uuid4())},
            )
            assert missing_user.status_code == 404

            global_create = await client.post(
                "/api/v1/aquaponics-systems",
                headers=headers,
                json={**catalog_payload, "owner_user_id": global_owner_id},
            )
            assert global_create.status_code == 201, global_create.text
            system_ids.append(global_create.json()["id"])
            assert global_create.json()["name"] == "Hệ thống Aquaponics"
            assert global_create.json()["owner_user_id"] == global_owner_id
            assert global_create.json()["owner_user_id"] != admin_id

            missing_owner = await client.post(
                "/api/v1/aquaponics-systems",
                headers=headers,
                json=catalog_payload,
            )
            assert missing_owner.status_code == 422

            patch_code = await client.patch(
                f"/api/v1/aquaponics-systems/{global_create.json()['id']}",
                headers=headers,
                json={"code": "CHANGED"},
            )
            assert patch_code.status_code == 422

            async with AsyncSessionLocal() as db:
                internal_system_ids = select(Project.id).where(
                    Project.public_id.in_(system_ids)
                )
                assert (
                    await db.scalar(
                        select(ProjectMember.id).where(
                            ProjectMember.project_id.in_(internal_system_ids),
                            ProjectMember.role == "OWNER",
                        )
                    )
                    is None
                )
    finally:
        await _cleanup_systems(system_ids)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()
