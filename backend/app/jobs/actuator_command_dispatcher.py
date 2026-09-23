from app.db.session import async_session_factory
from app.services.actuator_command_dispatch_service import dispatch_due_actuator_commands


async def dispatch_actuator_commands_once() -> int:
    async with async_session_factory() as db:
        return await dispatch_due_actuator_commands(db)
