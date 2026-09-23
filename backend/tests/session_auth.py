from __future__ import annotations

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.services.auth_session_service import create_user_session


async def session_headers(user: User | int) -> dict[str, str]:
    user_id = user if isinstance(user, int) else user.id
    async with AsyncSessionLocal() as db:
        row = await db.get(User, user_id)
        assert row is not None
        issued = await create_user_session(
            db,
            user=row,
            client_ip="127.0.0.1",
            user_agent="pytest-session-helper",
        )
        await db.commit()
    return {"Authorization": f"Bearer {issued.access_token}"}
