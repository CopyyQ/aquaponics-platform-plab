from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.enums import ProjectStatus, UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.permission import Role
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from tests.session_auth import session_headers


@pytest.mark.asyncio
async def test_owner_system_list_returns_only_owned_active_system() -> None:
    suffix = uuid4().hex[:8]
    disabled_project_id: int | None = None
    foreign_project_id: int | None = None
    foreign_owner_id: int | None = None
    membership_id: int | None = None

    async with AsyncSessionLocal() as db:
        owner = await db.scalar(
            select(User).where(User.username == "codex-test-owner")
        )
        admin = await db.scalar(
            select(User).where(User.system_role == UserRole.ADMIN)
        )
        owner_role = await db.scalar(select(Role).where(Role.code == "OWNER"))
        assert owner is not None and admin is not None and owner_role is not None

        owned_active = await db.scalar(
            select(Project).where(
                Project.owner_user_id == owner.id,
                Project.status == ProjectStatus.ACTIVE,
                Project.is_deleted.is_(False),
            )
        )
        assert owned_active is not None

        disabled = Project(
            owner_user_id=owner.id,
            code=f"OWNER-DISABLED-{suffix}",
            name="Owner disabled project",
            status=ProjectStatus.DISABLED,
        )
        db.add(disabled)
        await db.flush()
        disabled_project_id = disabled.id

        foreign_owner = User(
            username=f"owner-list-foreign-{suffix}",
            password_hash=hash_password("OwnerListForeign@123"),
            full_name="Foreign active owner",
            email=f"owner-list-foreign-{suffix}@example.test",
            phone_number=f"8{suffix[:7]}",
            address="",
            system_role=UserRole.OWNER,
            role_id=owner_role.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add(foreign_owner)
        await db.flush()
        foreign_owner_id = foreign_owner.id

        foreign_project = Project(
            owner_user_id=foreign_owner.id,
            code=f"FOREIGN-ACTIVE-{suffix}",
            name="Foreign active project",
            status=ProjectStatus.ACTIVE,
        )
        db.add(foreign_project)
        await db.flush()
        foreign_project_id = foreign_project.id

        membership = ProjectMember(
            project_id=foreign_project.id,
            user_id=owner.id,
            role="VIEWER",
            created_by=admin.id,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(membership)
        membership_id = membership.id

        owned_active_public_id = str(owned_active.public_id)
        disabled_public_id = str(disabled.public_id)

    owner_headers = await session_headers(owner)
    admin_headers = await session_headers(admin)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            owner_response = await client.get(
                "/api/v1/aquaponics-systems",
                headers=owner_headers,
            )
            assert owner_response.status_code == 200, owner_response.text
            owner_rows = owner_response.json()
            assert [row["id"] for row in owner_rows] == [owned_active_public_id]
            assert owner_rows[0]["status"] == ProjectStatus.ACTIVE.value

            admin_response = await client.get(
                "/api/v1/aquaponics-systems",
                headers=admin_headers,
            )
            assert admin_response.status_code == 200, admin_response.text
            admin_rows = admin_response.json()
            assert any(row["id"] == disabled_public_id for row in admin_rows)
    finally:
        async with AsyncSessionLocal() as db:
            if membership_id is not None:
                await db.execute(
                    delete(ProjectMember).where(ProjectMember.id == membership_id)
                )
            if foreign_project_id is not None:
                await db.execute(
                    delete(Project).where(Project.id == foreign_project_id)
                )
            if disabled_project_id is not None:
                await db.execute(
                    delete(Project).where(Project.id == disabled_project_id)
                )
            if foreign_owner_id is not None:
                await db.execute(delete(User).where(User.id == foreign_owner_id))
            await db.commit()
