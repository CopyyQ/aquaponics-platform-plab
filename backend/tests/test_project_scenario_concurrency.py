from __future__ import annotations

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.device import Device
from app.models.project import Project
from app.models.project_scenario import (
    ProjectScenario,
    ProjectScenarioBranch,
    ProjectScenarioItem,
)
from app.models.user import User
from tests.session_auth import session_headers


async def _context():
    async with AsyncSessionLocal() as db:
        project = await db.scalar(
            select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
        )
        admin = await db.scalar(
            select(User).where(User.system_role == UserRole.ADMIN)
        )
        assert project and admin
        device = await db.scalar(
            select(Device).where(Device.project_id == project.id)
        )
        assert device is not None
        return project, device, admin


async def _cleanup(db, device_id: int) -> None:
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
async def test_activation_returns_conflict_while_device_scenario_lock_is_busy() -> None:
    project, device, admin = await _context()
    async with AsyncSessionLocal() as db:
        await _cleanup(db, device.id)
        first = ProjectScenario(
            project_id=project.id,
            device_id=device.id,
            name="A",
            is_active=True,
            created_by=admin.id,
        )
        second = ProjectScenario(
            project_id=project.id,
            device_id=device.id,
            name="B",
            is_active=False,
            created_by=admin.id,
        )
        db.add_all([first, second])
        await db.commit()
        await db.refresh(second)
        target_public_id = second.public_id

    headers = await session_headers(admin)
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}"
        f"/devices/{device.public_id}/scenarios/{target_public_id}/activate"
    )

    blocker = AsyncSessionLocal()
    try:
        locked = bool(
            await blocker.scalar(
                select(func.pg_try_advisory_xact_lock(device.id))
            )
        )
        assert locked is True

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers)
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "SCENARIO_ACTIVATION_CONFLICT"

        async with AsyncSessionLocal() as db:
            active_count = int(
                await db.scalar(
                    select(func.count(ProjectScenario.id)).where(
                        ProjectScenario.device_id == device.id,
                        ProjectScenario.is_active.is_(True),
                        ProjectScenario.retired_at.is_(None),
                    )
                )
                or 0
            )
            active_name = await db.scalar(
                select(ProjectScenario.name).where(
                    ProjectScenario.device_id == device.id,
                    ProjectScenario.is_active.is_(True),
                    ProjectScenario.retired_at.is_(None),
                )
            )
            assert active_count == 1
            assert active_name == "A"
    finally:
        await blocker.rollback()
        await blocker.close()
        async with AsyncSessionLocal() as db:
            await _cleanup(db, device.id)
            await db.commit()
