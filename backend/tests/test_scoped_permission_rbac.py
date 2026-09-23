from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.core.enums import ProjectStatus, UserRole, UserStatus
from app.core.security import hash_password
from app.models.permission import Permission, Role, RoleAssignment, RolePermission, UserPermissionOverride
from app.models.project import Project
from app.models.user import User
from app.services.permission_service import get_effective_permissions, has_permission


@pytest.mark.asyncio
async def test_builtin_roles_are_distinct_and_admin_owns_rbac_management_permissions():
    async with AsyncSessionLocal() as db:
        roles = {r.code: r for r in (await db.scalars(select(Role))).all()}
        mappings = (await db.execute(
            select(Role.code, Permission.code).join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
        )).all()
        grants = {code: {permission for role, permission in mappings if role == code} for code in roles}
        assert {role.value for role in UserRole} == {"ADMIN", "OWNER", "VIEWER"}
        assert "TECHNICIAN" not in roles
        assert "roles.permissions.update" in grants["ADMIN"]
        assert "roles.permissions.update" not in grants["OWNER"]
        assert "permissions.read" not in grants["OWNER"]
        assert "roles.read" not in grants["VIEWER"]
        assert "sensors.thresholds.update" in grants["OWNER"]
        assert "actuators.commands.create" in grants["OWNER"]
        assert "incidents.acknowledge" in grants["OWNER"]
        assert "incidents.resolve" in grants["OWNER"]
        assert "actuators.commands.create" not in grants["VIEWER"]


@pytest.mark.asyncio
async def test_scoped_assignment_expiry_and_override_precedence():
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "codex-test-viewer"))
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        owner = await db.scalar(select(Role).where(Role.code == "OWNER"))
        permission = await db.scalar(select(Permission).where(Permission.code == "sensors.thresholds.update"))
        assert user and admin and owner and permission
        suffix = uuid4().hex[:8]
        secondary_owner = User(
            username=f"rbac-owner-{suffix}",
            password_hash=hash_password("RbacOwner@123"),
            full_name="RBAC secondary owner",
            email=f"rbac-owner-{suffix}@example.test",
            phone_number=f"06{suffix[:8]}",
            address="",
            system_role=UserRole.OWNER,
            role_id=owner.id,
            status=UserStatus.ACTIVE,
            must_change_password=False,
        )
        db.add(secondary_owner)
        await db.flush()
        systems = [
            Project(owner_user_id=admin.id, code=f"RBAC-SCOPE-A-{suffix}", name="RBAC scope A", status=ProjectStatus.ACTIVE),
            Project(owner_user_id=secondary_owner.id, code=f"RBAC-SCOPE-B-{suffix}", name="RBAC scope B", status=ProjectStatus.ACTIVE),
        ]
        db.add_all(systems); await db.flush()
        system_a, system_b = systems[0].id, systems[1].id
        await db.execute(delete(RoleAssignment).where(RoleAssignment.user_id == user.id))
        await db.execute(delete(UserPermissionOverride).where(UserPermissionOverride.user_id == user.id))
        db.add(RoleAssignment(user_id=user.id, role_id=owner.id, scope_type="AQUAPONICS_SYSTEM", scope_id=system_a))
        await db.commit()

        assert await has_permission(db, user, permission.code, system_a)
        assert not await has_permission(db, user, permission.code, system_b)

        assignment = await db.scalar(select(RoleAssignment).where(RoleAssignment.user_id == user.id))
        assignment.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.add(UserPermissionOverride(user_id=user.id, permission_id=permission.id, scope_type="GLOBAL", scope_id=None, effect="ALLOW"))
        db.add(UserPermissionOverride(user_id=user.id, permission_id=permission.id, scope_type="AQUAPONICS_SYSTEM", scope_id=system_a, effect="DENY"))
        await db.commit()
        assert permission.code in await get_effective_permissions(db, user, system_b)
        assert permission.code not in await get_effective_permissions(db, user, system_a)

        await db.execute(delete(RoleAssignment).where(RoleAssignment.user_id == user.id))
        await db.execute(delete(UserPermissionOverride).where(UserPermissionOverride.user_id == user.id))
        await db.execute(delete(Project).where(Project.id.in_([system_a, system_b])))
        await db.execute(delete(User).where(User.id == secondary_owner.id))
        await db.commit()
