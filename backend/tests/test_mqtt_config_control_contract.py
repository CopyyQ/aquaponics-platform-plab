from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator
from app.models.device import Device
from app.models.project import Project
from app.services.project_device_config_service import export_project_device_config


@pytest.mark.asyncio
async def test_mqtt_export_includes_command_and_ack_contract() -> None:
    suffix = uuid4().hex[:8].upper()
    actuator_id: int | None = None

    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        assert project is not None and device is not None
        actuator = Actuator(
            device_id=device.id,
            sequence_number=9901,
            code=f"CONFIG-PUMP-{suffix}",
            name="Bơm config regression",
            is_enabled=True,
        )
        db.add(actuator)
        await db.commit()
        await db.refresh(actuator)
        actuator_id = actuator.id

        try:
            exported = await export_project_device_config(db, project_id=project.id)
            config_device = next(item for item in exported.devices if item.id == device.public_id)
            config_actuator = next(item for item in config_device.actuators if item.id == actuator.public_id)

            assert config_device.topics.commands == f"aquaponics/{device.code}/commands"
            assert config_device.topics.command_ack == f"aquaponics/{device.code}/command-ack"
            assert config_actuator.control.capability == "ON_OFF"
            assert config_actuator.control.state_encoding.off is False
            assert config_actuator.control.state_encoding.on is True
            assert config_actuator.control.ack_required is True
        finally:
            if actuator_id is not None:
                await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
                await db.commit()
