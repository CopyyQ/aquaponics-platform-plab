from uuid import uuid4

import pytest
from fastapi import Request, Response
from sqlalchemy import delete, select

from app.api.v1.auth import login
from app.core.enums import UserRole, UserStatus
from app.core.exceptions import ApplicationError
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.permission import Role
from app.models.user import User
from app.schemas.auth import LoginRequest


@pytest.mark.asyncio
async def test_inactive_account_with_wrong_password_does_not_disclose_account_state() -> None:
    suffix = uuid4().hex[:8]
    username = f"disabled-login-{suffix}"
    user_id: int | None = None

    async with AsyncSessionLocal() as db:
        viewer_role = await db.scalar(select(Role).where(Role.code == "VIEWER"))
        assert viewer_role is not None
        user = User(
            username=username,
            password_hash=hash_password("CorrectPassword@123"),
            full_name="Disabled login regression",
            email=f"{username}@example.test",
            phone_number=f"09{suffix[:8]}",
            address="",
            system_role=UserRole.VIEWER,
            role_id=viewer_role.id,
            status=UserStatus.DISABLED,
            must_change_password=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

        try:
            with pytest.raises(ApplicationError) as caught:
                await login(
                    LoginRequest(
                        username=username,
                        password="WrongPassword@123",
                    ),
                    Request(
                        {
                            "type": "http",
                            "method": "POST",
                            "path": "/api/v1/auth/login",
                            "headers": [],
                            "client": ("127.0.0.1", 12345),
                            "server": ("testserver", 80),
                            "scheme": "http",
                            "query_string": b"",
                        }
                    ),
                    Response(),
                    db,
                )

            assert caught.value.code == "INVALID_CREDENTIALS"
            assert caught.value.status_code == 401
        finally:
            if user_id is not None:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
