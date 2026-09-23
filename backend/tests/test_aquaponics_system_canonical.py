from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.enums import UserRole
from tests.session_auth import session_headers
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.actuator import Actuator
from app.models.actuator_model import ActuatorModel
from app.models.device import Device
from app.models.device_template import DeviceTemplate, DeviceTemplateActuator, DeviceTemplateSensor
from app.models.project import Project
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.user import User


@pytest.mark.asyncio
async def test_aquaponics_system_device_can_own_sensors_and_actuators() -> None:
    suffix = uuid4().hex[:10].upper()
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        sensor_model = await db.scalar(select(SensorModel).where(SensorModel.is_active.is_(True)))
        actuator_model = await db.scalar(select(ActuatorModel).where(ActuatorModel.is_active.is_(True)))
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        assert admin and sensor_model and actuator_model and project
        headers = await session_headers(admin)
        system_id = str(project.public_id)

    device_id = None
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(f"/api/v1/aquaponics-systems/{system_id}", headers=headers)).status_code == 200
            device = await client.post(f"/api/v1/aquaponics-systems/{system_id}/devices", headers=headers, json={"code": f"DEVICE-{suffix}", "name": "Aquaponics Controller"})
            assert device.status_code == 201, device.text
            device_id = device.json()["id"]
            sensor_ids = []
            for index in range(2):
                response = await client.post(f"/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors", headers=headers, json={"sensor_model_id": sensor_model.id, "code": f"SENSOR-{suffix}-{index}", "name": f"Sensor {index}"})
                assert response.status_code == 201, response.text
                sensor_ids.append(response.json()["id"])
            actuator_ids = []
            for index in range(2):
                response = await client.post(f"/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators", headers=headers, json={"actuator_model_id": actuator_model.id, "code": f"ACTUATOR-{suffix}-{index}", "name": f"Actuator {index}"})
                assert response.status_code == 201, response.text
                actuator_ids.append(response.json()["id"])
            assert (await client.get(f"/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors/{sensor_ids[0]}", headers=headers)).status_code == 200
            assert (await client.get(f"/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_ids[0]}", headers=headers)).status_code == 200
            detail = await client.get(f"/api/v1/aquaponics-systems/{system_id}/devices/{device_id}", headers=headers)
            assert detail.status_code == 200, detail.text
            assert len(detail.json()["sensors"]) == 2
            assert len(detail.json()["actuators"]) == 2
    finally:
        async with AsyncSessionLocal() as db:
            if device_id:
                internal_device_id = await db.scalar(select(Device.id).where(Device.public_id == device_id))
                if internal_device_id:
                    await db.execute(delete(Actuator).where(Actuator.device_id == internal_device_id))
                    await db.execute(delete(Sensor).where(Sensor.device_id == internal_device_id))
                    await db.execute(delete(Device).where(Device.id == internal_device_id))
            await db.commit()


@pytest.mark.asyncio
async def test_device_template_mapping_and_provisioning_use_code_only() -> None:
    suffix = uuid4().hex[:10].upper()
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        sensor_model = await db.scalar(select(SensorModel).where(SensorModel.is_active.is_(True)))
        actuator_model = await db.scalar(select(ActuatorModel).where(ActuatorModel.is_active.is_(True)))
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        assert admin and sensor_model and actuator_model and project
        headers = await session_headers(admin)
        system_id = str(project.public_id)

    device_id = None
    template_id = 0
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            template = await client.post(
                "/api/v1/device-templates",
                headers=headers,
                json={"code": f"TPL-{suffix}", "name": "Template code regression"},
            )
            assert template.status_code == 201, template.text
            template_id = template.json()["id"]
            sensor_mapping = await client.post(
                f"/api/v1/device-templates/{template_id}/sensors",
                headers=headers,
                json={"sensor_model_id": sensor_model.id, "code": sensor_model.code, "is_required": False},
            )
            assert sensor_mapping.status_code == 201, sensor_mapping.text
            assert sensor_mapping.json()["code"] == sensor_model.code
            assert "sort_order" not in sensor_mapping.json()
            assert "slot" + "_code" not in sensor_mapping.json()
            actuator_mapping = await client.post(
                f"/api/v1/device-templates/{template_id}/actuators",
                headers=headers,
                json={"actuator_model_id": actuator_model.id, "code": actuator_model.code, "is_required": False},
            )
            assert actuator_mapping.status_code == 201, actuator_mapping.text
            assert actuator_mapping.json()["code"] == actuator_model.code
            assert "sort_order" not in actuator_mapping.json()
            assert "slot" + "_code" not in actuator_mapping.json()
            template_detail = await client.get(f"/api/v1/device-templates/{template_id}", headers=headers)
            assert template_detail.status_code == 200, template_detail.text
            assert "sort_order" not in str(template_detail.json())
            assert "slot" + "_code" not in str(template_detail.json())

            device = await client.post(
                f"/api/v1/aquaponics-systems/{system_id}/devices",
                headers=headers,
                json={"code": f"DEVICE-{suffix}", "name": "Device template regression", "device_template_id": template_id},
            )
            assert device.status_code == 201, device.text
            device_id = device.json()["id"]
            assert [item["code"] for item in device.json()["sensors"]] == [sensor_model.code]
            assert [item["code"] for item in device.json()["actuators"]] == [actuator_model.code]
    finally:
        async with AsyncSessionLocal() as db:
            if device_id:
                internal_device_id = await db.scalar(select(Device.id).where(Device.public_id == device_id))
                if internal_device_id:
                    await db.execute(delete(Actuator).where(Actuator.device_id == internal_device_id))
                    await db.execute(delete(Sensor).where(Sensor.device_id == internal_device_id))
                    await db.execute(delete(Device).where(Device.id == internal_device_id))
            if template_id:
                await db.execute(delete(DeviceTemplateSensor).where(DeviceTemplateSensor.device_template_id == template_id))
                await db.execute(delete(DeviceTemplateActuator).where(DeviceTemplateActuator.device_template_id == template_id))
                await db.execute(delete(DeviceTemplate).where(DeviceTemplate.id == template_id))
            await db.commit()
