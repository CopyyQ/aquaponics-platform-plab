from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import DeviceStatus
from app.core.exceptions import ApplicationError
from app.core.security import decrypt_secret, verify_hmac_signature
from app.models.device import Device, DeviceCredential


async def authenticate_device_request(
    db: AsyncSession,
    *,
    device_code: str,
    credential_version: int,
    timestamp: str,
    signature: str,
    raw_body: bytes,
) -> tuple[Device, DeviceCredential]:
    try:
        request_time = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (TypeError, ValueError, OSError):
        raise ApplicationError(
            "DEVICE_TIMESTAMP_INVALID",
            "Timestamp không hợp lệ",
            401,
        )

    age = abs((datetime.now(UTC) - request_time).total_seconds())
    if age > settings.device_signature_max_age_seconds:
        raise ApplicationError(
            "DEVICE_REQUEST_EXPIRED",
            "Request đã quá hạn",
            401,
        )

    device = await db.scalar(
        select(Device).where(Device.code == device_code, Device.is_deleted.is_(False))
    )
    if device is None or device.status == DeviceStatus.DISABLED:
        raise ApplicationError(
            "DEVICE_AUTH_INVALID",
            "Thiết bị không hợp lệ",
            401,
        )

    credential = await db.scalar(
        select(DeviceCredential).where(
            DeviceCredential.device_id == device.id,
            DeviceCredential.version == credential_version,
            DeviceCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise ApplicationError(
            "DEVICE_CREDENTIAL_INVALID",
            "Credential không hợp lệ",
            401,
        )
    if credential.expires_at and credential.expires_at < datetime.now(UTC):
        raise ApplicationError(
            "DEVICE_CREDENTIAL_EXPIRED",
            "Credential đã hết hạn",
            401,
        )

    secret = decrypt_secret(credential.secret_encrypted)
    if not verify_hmac_signature(secret, timestamp, raw_body, signature):
        raise ApplicationError(
            "DEVICE_SIGNATURE_INVALID",
            "Chữ ký thiết bị không hợp lệ",
            401,
        )
    return device, credential
