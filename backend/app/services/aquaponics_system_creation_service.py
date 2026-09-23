import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ProjectStatus, UserStatus
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.device_template import DeviceTemplate, DeviceTemplateActuator, DeviceTemplateSensor
from app.models.project import Project
from app.models.sensor import Sensor
from app.models.user import User
from app.services.actuator_identity_service import validate_local_actuator_code
from app.services.audit_service import write_audit
from app.services.project_scenario_sync_service import (
    clone_catalog_to_project_scenario,
)
from app.services.scenario_catalog_service import (
    ScenarioCatalogError,
    get_scenario_catalog,
)

CODE_GENERATION_ATTEMPTS = 8
DEFAULT_AQUAPONICS_SYSTEM_NAME = "Hệ thống Aquaponics"


class AquaponicsSystemCreationError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def generate_aquaponics_system_code(db: AsyncSession) -> str:
    for _ in range(CODE_GENERATION_ATTEMPTS):
        code = f"AQS-{secrets.token_hex(6).upper()}"
        if await db.scalar(select(Project.id).where(Project.code == code)) is None:
            return code
    raise AquaponicsSystemCreationError(
        "AQUAPONICS_SYSTEM_CODE_GENERATION_FAILED",
        "Không thể tạo mã Hệ thống Aquaponics duy nhất",
        503,
    )


async def _device_template(db: AsyncSession, template_id: int) -> DeviceTemplate:
    row = await db.scalar(
        select(DeviceTemplate)
        .options(
            selectinload(DeviceTemplate.sensor_mappings).selectinload(
                DeviceTemplateSensor.sensor_model
            ),
            selectinload(DeviceTemplate.actuator_mappings).selectinload(
                DeviceTemplateActuator.actuator_model
            ),
        )
        .where(
            DeviceTemplate.id == template_id,
            DeviceTemplate.is_deleted.is_(False),
            DeviceTemplate.is_active.is_(True),
        )
    )
    if row is None:
        raise AquaponicsSystemCreationError(
            "DEVICE_TEMPLATE_NOT_AVAILABLE",
            "Mẫu thiết bị không tồn tại hoặc không hoạt động",
            422,
        )
    return row


async def _ensure_single_system(db: AsyncSession, owner_user_id: int) -> None:
    existing = await db.scalar(
        select(Project.id).where(Project.owner_user_id == owner_user_id)
    )
    if existing is not None:
        raise AquaponicsSystemCreationError(
            "OWNER_ALREADY_HAS_AQUAPONICS_SYSTEM",
            "Mỗi người dùng chỉ được sở hữu một Hệ thống Aquaponics",
            409,
        )


async def _materialize_device(
    db: AsyncSession,
    *,
    system: Project,
    template: DeviceTemplate,
) -> Device:
    device = Device(
        project_id=system.id,
        device_template_id=template.id,
        code=f"{system.code}-MAIN",
        name=template.name,
        description=template.description,
        is_enabled=True,
    )
    db.add(device)
    await db.flush()

    for mapping in template.sensor_mappings:
        db.add(
            Sensor(
                device_id=device.id,
                sensor_model_id=mapping.sensor_model_id,
                code=mapping.code,
                name=mapping.display_name or mapping.sensor_model.name,
                installation_location=mapping.default_location,
                is_enabled=True,
            )
        )

    for sequence_number, mapping in enumerate(template.actuator_mappings, start=1):
        db.add(
            Actuator(
                device_id=device.id,
                actuator_model_id=mapping.actuator_model_id,
                sequence_number=sequence_number,
                code=validate_local_actuator_code(
                    mapping.code,
                    project_code=system.code,
                    device_code=device.code,
                ),
                name=mapping.default_name or mapping.actuator_model.name,
                location=mapping.default_location,
                notes=mapping.default_notes,
                is_enabled=mapping.is_enabled,
                desired_state=mapping.default_state,
            )
        )
    await db.flush()
    return device


async def create_aquaponics_system(
    db: AsyncSession,
    *,
    owner_user_id: int,
    actor_id: int,
    device_template_id: int,
    scenario_catalog_id: int,
) -> Project:
    owner = await db.scalar(
        select(User).where(User.id == owner_user_id, User.is_deleted.is_(False))
    )
    if owner is None:
        raise AquaponicsSystemCreationError(
            "OWNER_NOT_FOUND", "Không tìm thấy chủ hệ thống", 404
        )
    if owner.status != UserStatus.ACTIVE:
        raise AquaponicsSystemCreationError(
            "OWNER_NOT_ACTIVE", "Chủ hệ thống phải đang hoạt động", 422
        )

    await _ensure_single_system(db, owner_user_id)
    template = await _device_template(db, device_template_id)
    try:
        scenario_catalog = await get_scenario_catalog(
            db, scenario_catalog_id, active_only=True
        )
    except ScenarioCatalogError as exc:
        raise AquaponicsSystemCreationError(
            exc.code, exc.message, exc.status_code
        ) from exc
    if scenario_catalog.device_template_id != template.id:
        raise AquaponicsSystemCreationError(
            "SCENARIO_CATALOG_DEVICE_MISMATCH",
            "Kịch bản không thuộc thiết bị đã chọn",
            422,
        )

    item: Project | None = None
    for _ in range(CODE_GENERATION_ATTEMPTS):
        candidate = Project(
            owner_user_id=owner_user_id,
            code=await generate_aquaponics_system_code(db),
            name=DEFAULT_AQUAPONICS_SYSTEM_NAME,
            device_template_id=template.id,
            scenario_catalog_id=scenario_catalog.id,
            status=ProjectStatus.ACTIVE,
        )
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            item = candidate
            break
        except IntegrityError:
            if await db.scalar(
                select(Project.id).where(Project.owner_user_id == owner_user_id)
            ):
                raise AquaponicsSystemCreationError(
                    "OWNER_ALREADY_HAS_AQUAPONICS_SYSTEM",
                    "Mỗi người dùng chỉ được sở hữu một Hệ thống Aquaponics",
                    409,
                )
            continue

    if item is None:
        raise AquaponicsSystemCreationError(
            "AQUAPONICS_SYSTEM_CODE_GENERATION_FAILED",
            "Không thể tạo mã Hệ thống Aquaponics duy nhất",
            503,
        )

    try:
        device = await _materialize_device(db, system=item, template=template)
        project_scenario = await clone_catalog_to_project_scenario(
            db,
            catalog=scenario_catalog,
            device=device,
            actor_id=actor_id,
            name=scenario_catalog.name,
        )
        await write_audit(
            db,
            user_id=actor_id,
            project_id=item.id,
            action="CREATE_AQUAPONICS_SYSTEM",
            entity_type="AQUAPONICS_SYSTEM",
            entity_id=item.id,
            new_data={
                "code": item.code,
                "name": item.name,
                "owner_user_id": owner_user_id,
                "device_template_id": template.id,
                "scenario_catalog_id": scenario_catalog.id,
                "project_scenario_id": project_scenario.id,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(item)
    return item
