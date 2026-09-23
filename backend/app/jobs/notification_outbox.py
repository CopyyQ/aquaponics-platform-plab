from app.db.session import AsyncSessionLocal
from app.services.notification_outbox_service import process_notification_outbox


async def dispatch_operational_notifications() -> None:
    async with AsyncSessionLocal() as db:
        await process_notification_outbox(db)
