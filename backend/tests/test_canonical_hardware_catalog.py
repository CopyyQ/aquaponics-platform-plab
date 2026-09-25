import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1.canonical_catalogs import (
    ActuatorModelCreate,
    ActuatorModelRead,
    ActuatorModelUpdate,
    TemplateActuatorSlotCreate,
    TemplateActuatorSlotRead,
    TemplateActuatorSlotUpdate,
    TemplateSensorSlotCreate,
    TemplateSensorSlotRead,
    TemplateSensorSlotUpdate,
)
from app.db.session import AsyncSessionLocal
from app.models.actuator_model import ActuatorModel
from app.models.device_template import (
    DeviceTemplate,
    DeviceTemplateActuator,
    DeviceTemplateSensor,
)
from app.models.sensor_model import SensorModel
from scripts.seed import (
    ACTUATOR_MODELS,
    CANONICAL_DEVICE_TEMPLATE_CODE,
    CANONICAL_DEVICE_TEMPLATE_NAME,
    SENSOR_MODELS,
)


EXPECTED_SENSOR_CODES = (
    "NH3",
    "NO3",
    "PH",
    "DO",
    "TDS",
    "WATER_TEMPERATURE",
    "WATER_LEVEL",
    "WATER_LEVELW2",
    "AIR_TEMPERATURE",
    "AIR_HUMIDITY",
    "LIGHT_INTENSITY",
    "VOLTAGE",
    "CURRENT",
)

EXPECTED_ACTUATOR_CODES = (
    "FISH_TANK_PUMP",
    "BIOFILTER_PUMP",
    "AERATION_PUMP",
    "FRESH_WATER_VALVE",
    "FILTER_DRAIN_VALVE",
    "GROW_LIGHT",
    "WARNING_LIGHT",
    "WARNING_BUZZER",
)


def test_sensor_catalog_is_exactly_the_approved_aquaponics_set() -> None:
    codes = tuple(item["code"] for item in SENSOR_MODELS)
    assert codes == EXPECTED_SENSOR_CODES
    assert len(codes) == len(set(codes)) == 13


def test_actuator_catalog_is_exactly_the_approved_aquaponics_set() -> None:
    codes = tuple(item[0] for item in ACTUATOR_MODELS)
    assert codes == EXPECTED_ACTUATOR_CODES
    assert len(codes) == len(set(codes)) == 8


def test_canonical_device_template_identity() -> None:
    assert CANONICAL_DEVICE_TEMPLATE_CODE == "AQUAPONICS_SYSTEM_DEVICE"
    assert CANONICAL_DEVICE_TEMPLATE_NAME == "Thiết bị hệ thống Aquaponics"


@pytest.mark.asyncio
async def test_seed_persists_exact_canonical_hardware_catalog() -> None:
    async with AsyncSessionLocal() as db:
        sensor_codes = tuple(
            (await db.scalars(select(SensorModel.code).order_by(SensorModel.code))).all()
        )
        actuator_codes = tuple(
            (await db.scalars(select(ActuatorModel.code).order_by(ActuatorModel.code))).all()
        )
        templates = list(
            (
                await db.scalars(
                    select(DeviceTemplate).where(DeviceTemplate.is_deleted.is_(False))
                )
            ).all()
        )

        assert set(sensor_codes) == set(EXPECTED_SENSOR_CODES)
        assert len(sensor_codes) == 13
        assert set(actuator_codes) == set(EXPECTED_ACTUATOR_CODES)
        assert len(actuator_codes) == 8
        assert len(templates) == 1

        template = templates[0]
        assert template.code == CANONICAL_DEVICE_TEMPLATE_CODE
        assert template.name == CANONICAL_DEVICE_TEMPLATE_NAME

        sensor_slots = list(
            (
                await db.scalars(
                    select(DeviceTemplateSensor)
                    .where(DeviceTemplateSensor.device_template_id == template.id)
                    .order_by(DeviceTemplateSensor.id)
                )
            ).all()
        )
        actuator_slots = list(
            (
                await db.scalars(
                    select(DeviceTemplateActuator)
                    .where(DeviceTemplateActuator.device_template_id == template.id)
                    .order_by(DeviceTemplateActuator.id)
                )
            ).all()
        )

        assert tuple(slot.code for slot in sensor_slots) == EXPECTED_SENSOR_CODES
        assert tuple(slot.code for slot in actuator_slots) == EXPECTED_ACTUATOR_CODES
        assert all(slot.is_required for slot in sensor_slots)
        assert all(slot.is_required for slot in actuator_slots)


def test_actuator_model_has_no_sort_order_contract() -> None:
    assert "sort_order" not in ActuatorModel.__table__.c
    assert "sort_order" not in ActuatorModelCreate.model_fields
    assert "sort_order" not in ActuatorModelUpdate.model_fields
    assert "sort_order" not in ActuatorModelRead.model_fields


def test_actuator_model_rejects_removed_sort_order() -> None:
    with pytest.raises(ValidationError):
        ActuatorModelCreate(code="TEST_PUMP", name="Test pump", sort_order=99)
    with pytest.raises(ValidationError):
        ActuatorModelUpdate(sort_order=88)


def test_template_mappings_have_no_sort_order_contract() -> None:
    assert "sort_order" not in DeviceTemplateSensor.__table__.c
    assert "sort_order" not in DeviceTemplateActuator.__table__.c
    for schema in (
        TemplateSensorSlotCreate,
        TemplateSensorSlotUpdate,
        TemplateSensorSlotRead,
        TemplateActuatorSlotCreate,
        TemplateActuatorSlotUpdate,
        TemplateActuatorSlotRead,
    ):
        assert "sort_order" not in schema.model_fields
