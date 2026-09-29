from __future__ import annotations

import importlib

import pytest
from sqlalchemy import func, select

from app.core.enums import ProjectStatus
from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator
from app.models.actuator_model import ActuatorModel
from app.models.automatic_feeder import (
    AutomaticFeederConfig,
    AutomaticFeederScheduleSlot,
    FeedLevel,
)
from app.models.device import Device
from app.models.device_template import DeviceTemplate, DeviceTemplateActuator
from app.models.project import Project
from app.models.user import User
from app.schemas.device_template import TemplateActuatorInput, TemplateActuatorUpdate
from app.services.aquaponics_system_creation_service import (
    _device_template,
    _materialize_device,
)
from scripts.seed import CANONICAL_DEVICE_TEMPLATE_CODE

FEEDER_MODEL_CODE = "AUTOMATIC_FEEDER"
EXPECTED_DEFAULT_TIMES = ("00:00:00", "08:00:00", "16:00:00")


def test_template_schema_accepts_feeder_control_contract() -> None:
    created = TemplateActuatorInput(
        actuator_model_id=1,
        code=FEEDER_MODEL_CODE,
        actuator_type="FEEDER",
        command_capability="FEED_CONTROL",
    )
    updated = TemplateActuatorUpdate(
        actuator_type="FEEDER",
        command_capability="FEED_CONTROL",
    )

    assert created.actuator_type == "FEEDER"
    assert created.command_capability == "FEED_CONTROL"
    assert updated.actuator_type == "FEEDER"
    assert updated.command_capability == "FEED_CONTROL"


@pytest.mark.asyncio
async def test_seed_persists_feeder_model_and_template_mapping() -> None:
    async with AsyncSessionLocal() as db:
        model = await db.scalar(
            select(ActuatorModel).where(ActuatorModel.code == FEEDER_MODEL_CODE)
        )
        assert model is not None
        template = await db.scalar(
            select(DeviceTemplate).where(
                DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE
            )
        )
        assert template is not None
        mapping = await db.scalar(
            select(DeviceTemplateActuator).where(
                DeviceTemplateActuator.device_template_id == template.id,
                DeviceTemplateActuator.actuator_model_id == model.id,
            )
        )
        assert mapping is not None
        assert mapping.actuator_type == "FEEDER"
        assert mapping.command_capability == "FEED_CONTROL"
        assert mapping.is_required is True


@pytest.mark.asyncio
async def test_materialized_feeder_gets_default_editable_schedule() -> None:
    async with AsyncSessionLocal() as db:
        owner_id = await db.scalar(select(User.id).order_by(User.id).limit(1))
        template_id = await db.scalar(
            select(DeviceTemplate.id).where(
                DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE
            )
        )
        assert owner_id is not None and template_id is not None
        template = await _device_template(db, template_id)
        project = Project(
            owner_user_id=owner_id,
            code="FEEDER-TDD-MATERIALIZE",
            name="Feeder TDD",
            status=ProjectStatus.ACTIVE,
            device_template_id=template.id,
        )
        db.add(project)
        await db.flush()

        device = await _materialize_device(db, system=project, template=template)
        feeder = await db.scalar(
            select(Actuator)
            .join(ActuatorModel, ActuatorModel.id == Actuator.actuator_model_id)
            .where(
                Actuator.device_id == device.id,
                ActuatorModel.code == FEEDER_MODEL_CODE,
            )
        )
        assert feeder is not None
        config = await db.scalar(
            select(AutomaticFeederConfig).where(
                AutomaticFeederConfig.actuator_id == feeder.id
            )
        )
        assert config is not None
        assert config.feed_level == FeedLevel.LEVEL_1.value
        assert config.schedule_enabled is True
        slots = list(
            (
                await db.scalars(
                    select(AutomaticFeederScheduleSlot)
                    .where(AutomaticFeederScheduleSlot.feeder_config_id == config.id)
                    .order_by(AutomaticFeederScheduleSlot.slot_number)
                )
            ).all()
        )
        assert tuple(str(slot.feed_time) for slot in slots) == EXPECTED_DEFAULT_TIMES
        await db.rollback()


@pytest.mark.asyncio
async def test_existing_template_device_backfill_is_idempotent() -> None:
    seed_module = importlib.import_module("scripts.seed")
    backfill = getattr(seed_module, "backfill_automatic_feeder_resources", None)
    assert callable(backfill), "automatic feeder backfill is missing"

    async with AsyncSessionLocal() as db:
        owner_id = await db.scalar(select(User.id).order_by(User.id).limit(1))
        template = await db.scalar(
            select(DeviceTemplate).where(
                DeviceTemplate.code == CANONICAL_DEVICE_TEMPLATE_CODE
            )
        )
        assert owner_id is not None and template is not None
        project = Project(
            owner_user_id=owner_id,
            code="FEEDER-TDD-BACKFILL",
            name="Feeder Backfill TDD",
            status=ProjectStatus.ACTIVE,
            device_template_id=template.id,
        )
        db.add(project)
        await db.flush()
        device = Device(
            project_id=project.id,
            device_template_id=template.id,
            code="FEEDER-TDD-DEVICE",
            name="Feeder TDD Device",
            is_enabled=True,
        )
        db.add(device)
        await db.flush()

        await backfill(db, template.id, actor_id=owner_id)
        await backfill(db, template.id, actor_id=owner_id)

        feeder_model_id = await db.scalar(
            select(ActuatorModel.id).where(ActuatorModel.code == FEEDER_MODEL_CODE)
        )
        assert feeder_model_id is not None
        feeder_count = int(
            await db.scalar(
                select(func.count(Actuator.id)).where(
                    Actuator.device_id == device.id,
                    Actuator.actuator_model_id == feeder_model_id,
                    Actuator.is_deleted.is_(False),
                )
            )
            or 0
        )
        assert feeder_count == 1
        feeder = await db.scalar(
            select(Actuator).where(
                Actuator.device_id == device.id,
                Actuator.actuator_model_id == feeder_model_id,
            )
        )
        assert feeder is not None
        config = await db.scalar(
            select(AutomaticFeederConfig).where(
                AutomaticFeederConfig.actuator_id == feeder.id
            )
        )
        assert config is not None
        slot_count = int(
            await db.scalar(
                select(func.count(AutomaticFeederScheduleSlot.id)).where(
                    AutomaticFeederScheduleSlot.feeder_config_id == config.id
                )
            )
            or 0
        )
        assert slot_count == 3
        await db.rollback()


def test_feeder_catalog_uses_canonical_vietnamese_identity() -> None:
    from scripts.seed import ACTUATOR_MODELS

    feeder = next(item for item in ACTUATOR_MODELS if item[0] == FEEDER_MODEL_CODE)
    assert feeder[1] == "Máy cho ăn tự động"
    assert feeder[2] == "Cấp thức ăn cho cá theo mức và lịch cấu hình."
