from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.enums import DeviceStatus, ProjectStatus, UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.device import Device
from app.models.permission import Role
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.user import User
from scripts.seed import seed_rbac
from tests.session_auth import session_headers


async def _context():
    async with AsyncSessionLocal() as db:
        project = await db.scalar(
            select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
        )
        owner = await db.scalar(
            select(User).where(User.username == "codex-test-owner")
        )
        viewer = await db.scalar(
            select(User).where(User.username == "codex-test-viewer")
        )
        admin = await db.scalar(
            select(User).where(User.system_role == UserRole.ADMIN)
        )
        assert project and owner and viewer and admin
        device = await db.scalar(
            select(Device).where(Device.project_id == project.id)
        )
        assert device is not None
        return project, device, owner, viewer, admin


async def _cleanup_device_scenarios(db, device_id: int) -> None:
    scenario_ids = select(ProjectScenario.id).where(
        ProjectScenario.device_id == device_id
    )
    item_ids = select(ProjectScenarioItem.id).where(
        ProjectScenarioItem.project_scenario_id.in_(scenario_ids)
    )
    await db.execute(
        delete(ProjectScenarioBranch).where(
            ProjectScenarioBranch.project_scenario_item_id.in_(item_ids)
        )
    )
    await db.execute(
        delete(ProjectScenarioItem).where(
            ProjectScenarioItem.project_scenario_id.in_(scenario_ids)
        )
    )
    await db.execute(
        delete(ProjectScenario).where(ProjectScenario.device_id == device_id)
    )


@pytest.mark.asyncio
async def test_owner_admin_and_viewer_project_scenario_api_matrix() -> None:
    project, device, owner, viewer, admin = await _context()
    async with AsyncSessionLocal() as db:
        await seed_rbac(db)
        member = await db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == viewer.id,
            )
        )
        if member is None:
            db.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=viewer.id,
                    role="VIEWER",
                    created_by=admin.id,
                )
            )
        await _cleanup_device_scenarios(db, device.id)
        await db.commit()

    owner_headers = await session_headers(owner)
    viewer_headers = await session_headers(viewer)
    admin_headers = await session_headers(admin)
    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}"
        f"/devices/{device.public_id}/scenarios"
    )

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            owner_created = await client.post(
                base,
                headers=owner_headers,
                json={"name": "Kịch bản Owner", "description": "owner"},
            )
            assert owner_created.status_code == 201, owner_created.text
            owner_id = owner_created.json()["id"]

            viewer_list = await client.get(base, headers=viewer_headers)
            assert viewer_list.status_code == 200, viewer_list.text
            assert any(row["id"] == owner_id for row in viewer_list.json())

            viewer_create = await client.post(
                base,
                headers=viewer_headers,
                json={"name": "Viewer không được tạo"},
            )
            assert viewer_create.status_code == 403, viewer_create.text

            owner_updated = await client.patch(
                f"{base}/{owner_id}",
                headers=owner_headers,
                json={"name": "Kịch bản Owner đã sửa"},
            )
            assert owner_updated.status_code == 200, owner_updated.text
            assert owner_updated.json()["name"] == "Kịch bản Owner đã sửa"

            admin_clone = await client.post(
                f"{base}/{owner_id}/clone",
                headers=admin_headers,
                json={"name": "Kịch bản Admin clone"},
            )
            assert admin_clone.status_code == 201, admin_clone.text
            clone_id = admin_clone.json()["id"]

            activated = await client.post(
                f"{base}/{clone_id}/activate",
                headers=admin_headers,
            )
            assert activated.status_code == 200, activated.text
            assert activated.json()["scenario"]["id"] == clone_id
            assert activated.json()["scenario"]["is_active"] is True

            delete_active = await client.delete(
                f"{base}/{clone_id}",
                headers=owner_headers,
            )
            assert delete_active.status_code == 409, delete_active.text

            delete_inactive = await client.delete(
                f"{base}/{owner_id}",
                headers=admin_headers,
            )
            assert delete_inactive.status_code == 204, delete_inactive.text
    finally:
        async with AsyncSessionLocal() as db:
            await _cleanup_device_scenarios(db, device.id)
            await db.execute(
                delete(ProjectMember).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == viewer.id,
                )
            )
            await db.commit()


@pytest.mark.asyncio
async def test_owner_cannot_access_foreign_project_scenario() -> None:
    _, _, owner, _, admin = await _context()
    suffix = uuid4().hex[:8]
    foreign_owner_id = None
    foreign_project_id = None
    foreign_device_id = None

    async with AsyncSessionLocal() as db:
        owner_role = await db.scalar(select(Role).where(Role.code == "OWNER"))
        assert owner_role is not None
        foreign_owner = User(
            username=f"scenario-foreign-{suffix}",
            password_hash=hash_password("ScenarioForeign@123"),
            full_name="Foreign scenario owner",
            email=f"scenario-foreign-{suffix}@example.test",
            phone_number=f"9{suffix[:7]}",
            address="",
            system_role=UserRole.OWNER,
            role_id=owner_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add(foreign_owner)
        await db.flush()
        foreign_project = Project(
            owner_user_id=foreign_owner.id,
            code=f"SCN-FOREIGN-{suffix}",
            name="Foreign project",
            status=ProjectStatus.ACTIVE,
        )
        db.add(foreign_project)
        await db.flush()
        foreign_device = Device(
            project_id=foreign_project.id,
            code=f"FOREIGN-{suffix}",
            name="Foreign device",
            status=DeviceStatus.ONLINE,
            is_enabled=True,
        )
        db.add(foreign_device)
        await db.flush()
        scenario = ProjectScenario(
            project_id=foreign_project.id,
            device_id=foreign_device.id,
            name="Foreign scenario",
            is_active=False,
            created_by=admin.id,
        )
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)
        foreign_owner_id = foreign_owner.id
        foreign_project_id = foreign_project.id
        foreign_device_id = foreign_device.id
        system_public = foreign_project.public_id
        device_public = foreign_device.public_id
        scenario_public = scenario.public_id

    owner_headers = await session_headers(owner)
    base = (
        f"/api/v1/aquaponics-systems/{system_public}"
        f"/devices/{device_public}/scenarios/{scenario_public}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = [
                await client.get(base, headers=owner_headers),
                await client.patch(
                    base,
                    headers=owner_headers,
                    json={"name": "Không được sửa"},
                ),
                await client.post(
                    f"{base}/activate",
                    headers=owner_headers,
                ),
                await client.delete(base, headers=owner_headers),
            ]
        assert all(response.status_code in {403, 404} for response in responses)
    finally:
        async with AsyncSessionLocal() as db:
            if foreign_device_id is not None:
                await _cleanup_device_scenarios(db, foreign_device_id)
                await db.execute(
                    delete(Device).where(Device.id == foreign_device_id)
                )
            if foreign_project_id is not None:
                await db.execute(
                    delete(Project).where(Project.id == foreign_project_id)
                )
            if foreign_owner_id is not None:
                await db.execute(
                    delete(User).where(User.id == foreign_owner_id)
                )
            await db.commit()
