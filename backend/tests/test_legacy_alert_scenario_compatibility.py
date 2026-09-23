from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.actuator import Actuator
from app.models.actuator_model import ActuatorModel
from app.models.device import Device
from app.models.operational_alert import AlertRule, NotificationOutbox, OperationalIncident
from app.models.project import Project
from app.models.project_scenario import ProjectScenario
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.threshold_alert_config import ThresholdAlertConfig
from app.models.user import User
from app.services.operational_incident_service import (
    evaluate_alert_scenarios_for_actuator,
    evaluate_operational_rules_for_sensor,
)
from tests.session_auth import session_headers


async def runtime():
    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        assert project is not None
        device = await db.scalar(select(Device).where(Device.project_id == project.id))
        owner = await db.get(User, project.owner_user_id)
        admin = await db.scalar(select(User).where(User.username == "admin"))
        assert device is not None and owner is not None and admin is not None
        return project, device, owner, admin


@pytest.mark.asyncio
async def test_scenario_crud_containment_and_sensor_actuator_lifecycle() -> None:
    project, device, owner, admin = await runtime(); suffix = uuid4().hex[:8].upper(); now = datetime.now(UTC)
    owner_headers = await session_headers(owner)
    admin_headers = await session_headers(admin)
    async with AsyncSessionLocal() as db:
        sensor_model = await db.scalar(select(SensorModel).where(SensorModel.code == "PH")); actuator_model = await db.scalar(select(ActuatorModel).limit(1))
        assert sensor_model is not None and actuator_model is not None
        sensor = Sensor(device_id=device.id, sensor_model_id=sensor_model.id, code=f"SCN-S-{suffix}", name="Scenario sensor", is_enabled=True)
        actuator = Actuator(device_id=device.id, actuator_model_id=actuator_model.id, sequence_number=992,
            code=f"SCN-A-{suffix}", name="ÄÃ¨n chiáº¿u sÃ¡ng", is_enabled=True, desired_state=True,
            reported_state=True, voltage_v=12, current_a=0)
        db.add_all([sensor, actuator]); await db.commit()
        sensor_public, actuator_public = sensor.public_id, actuator.public_id
        sensor_internal, actuator_internal = sensor.id, actuator.id
    base = f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        sensor_create = await client.post(f"{base}/sensors/{sensor_public}/alert-scenarios", headers=owner_headers, json={
            "name": "pH ngoÃ i khoáº£ng", "risk_level": "HIGH", "duration_seconds": 0,
            "range_mode": "OUTSIDE_RANGE", "range": {"min": 6.5, "max": 8.0}})
        assert sensor_create.status_code == 201, sensor_create.text
        sensor_scenario_id = sensor_create.json()["id"]; assert isinstance(sensor_scenario_id, str)
        actuator_create = await client.post(f"{base}/actuators/{actuator_public}/alert-scenarios", headers=admin_headers, json={
            "name": "ÄÃ¨n báº­t nhÆ°ng khÃ´ng cÃ³ táº£i", "risk_level": "VERY_HIGH", "duration_seconds": 0,
            "reported_state": True, "voltage": {"min": 11, "max": 13}, "current": {"min": 0, "max": 0}})
        assert actuator_create.status_code == 201, actuator_create.text
        actuator_scenario_id = actuator_create.json()["id"]
        assert (await client.get(f"{base}/actuators/{actuator_public}/alert-scenarios", headers=admin_headers)).status_code == 200
        wrong = await client.get(f"/api/v1/aquaponics-systems/{project.public_id}/devices/{uuid4()}/actuators/{actuator_public}/alert-scenarios/{actuator_scenario_id}", headers=admin_headers)
        assert wrong.status_code == 404
    async with AsyncSessionLocal() as db:
        sensor = await db.get(Sensor, sensor_internal); actuator = await db.get(Actuator, actuator_internal); device_row = await db.get(Device, device.id)
        assert sensor is not None and actuator is not None and device_row is not None
        await evaluate_operational_rules_for_sensor(db, sensor=sensor, value=6.0, quality="VALID", recorded_at=now, received_at=now)
        await evaluate_alert_scenarios_for_actuator(db, device=device_row, actuator=actuator, recorded_at=now, received_at=now)
        await db.commit()
        sensor_incident = await db.scalar(select(OperationalIncident).where(OperationalIncident.sensor_id == sensor.id, OperationalIncident.status == "OPEN"))
        actuator_incident = await db.scalar(select(OperationalIncident).where(OperationalIncident.actuator_id == actuator.id, OperationalIncident.status == "OPEN"))
        assert sensor_incident is not None and actuator_incident is not None
        assert actuator_incident.trigger_snapshot["reported_state"] is True
        await evaluate_operational_rules_for_sensor(db, sensor=sensor, value=7.0, quality="VALID", recorded_at=now + timedelta(seconds=1), received_at=now + timedelta(seconds=1))
        await evaluate_operational_rules_for_sensor(db, sensor=sensor, value=6.0, quality="VALID", recorded_at=now + timedelta(seconds=2), received_at=now + timedelta(seconds=2))
        await db.commit(); assert sensor_incident.status == "RESOLVED"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.patch(f"{base}/actuators/{actuator_public}/alert-scenarios/{actuator_scenario_id}", headers=admin_headers, json={"is_enabled": False})).status_code == 200
        assert (await client.delete(f"{base}/sensors/{sensor_public}/alert-scenarios/{sensor_scenario_id}", headers=owner_headers)).status_code == 204
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(OperationalIncident.id).where(OperationalIncident.actuator_id == actuator_internal, OperationalIncident.status == "NORMALIZED"))
        assert await db.scalar(select(OperationalIncident.id).where(OperationalIncident.sensor_id == sensor_internal, OperationalIncident.status == "NORMALIZED"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.patch(f"{base}/actuators/{actuator_public}/alert-scenarios/{actuator_scenario_id}", headers=admin_headers, json={"is_enabled": True})).status_code == 200
    async with AsyncSessionLocal() as db:
        actuator = await db.get(Actuator, actuator_internal); device_row = await db.get(Device, device.id)
        assert actuator is not None and device_row is not None
        actuator.reported_state = True
        await evaluate_alert_scenarios_for_actuator(db, device=device_row, actuator=actuator, recorded_at=now + timedelta(seconds=3), received_at=now + timedelta(seconds=3))
        reopened = await db.scalar(select(OperationalIncident).where(OperationalIncident.actuator_id == actuator.id, OperationalIncident.status == "OPEN"))
        assert reopened is not None
        actuator.reported_state = False
        await evaluate_alert_scenarios_for_actuator(db, device=device_row, actuator=actuator, recorded_at=now + timedelta(seconds=4), received_at=now + timedelta(seconds=4))
        await db.commit(); assert reopened.status == "NORMALIZED"
    async with AsyncSessionLocal() as db:
        incident_ids = select(OperationalIncident.id).where((OperationalIncident.sensor_id == sensor_internal) | (OperationalIncident.actuator_id == actuator_internal))
        await db.execute(delete(NotificationOutbox).where(NotificationOutbox.incident_id.in_(incident_ids)))
        await db.execute(delete(OperationalIncident).where(OperationalIncident.id.in_(incident_ids)))
        await db.execute(delete(Sensor).where(Sensor.id == sensor_internal)); await db.execute(delete(Actuator).where(Actuator.id == actuator_internal))
        await db.execute(delete(AlertRule).where(AlertRule.public_id.in_([sensor_scenario_id, actuator_scenario_id]))); await db.commit()


@pytest.mark.asyncio
async def test_project_scenario_managed_device_rejects_legacy_runtime_mutations() -> None:
    project, device, owner, admin = await runtime()
    suffix = uuid4().hex[:8].upper()
    owner_headers = await session_headers(owner)
    admin_headers = await session_headers(admin)
    sensor_rule_id: str | None = None
    actuator_rule_id: str | None = None
    sensor_internal: int | None = None
    actuator_internal: int | None = None

    async with AsyncSessionLocal() as db:
        sensor_model = await db.scalar(
            select(SensorModel).where(SensorModel.code == "PH")
        )
        actuator_model = await db.scalar(select(ActuatorModel).limit(1))
        assert sensor_model is not None and actuator_model is not None
        max_sequence = (
            await db.scalar(
                select(Actuator.sequence_number)
                .where(Actuator.device_id == device.id)
                .order_by(Actuator.sequence_number.desc())
                .limit(1)
            )
            or 0
        )
        sensor = Sensor(
            device_id=device.id,
            sensor_model_id=sensor_model.id,
            code=f"LOCK-S-{suffix}",
            name="Managed sensor",
            is_enabled=True,
        )
        actuator = Actuator(
            device_id=device.id,
            actuator_model_id=actuator_model.id,
            sequence_number=max_sequence + 400,
            code=f"LOCK-A-{suffix}",
            name="Managed actuator",
            is_enabled=True,
        )
        db.add_all([sensor, actuator])
        await db.commit()
        sensor_public = sensor.public_id
        actuator_public = actuator.public_id
        sensor_internal = sensor.id
        actuator_internal = actuator.id

    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}"
        f"/devices/{device.public_id}"
    )
    scenario_payload = {
        "name": "Legacy rule before cutover",
        "risk_level": "HIGH",
        "duration_seconds": 0,
        "range_mode": "OUTSIDE_RANGE",
        "range": {"min": 6.5, "max": 8.0},
    }
    actuator_scenario_payload = {
        "name": "Legacy actuator before cutover",
        "risk_level": "HIGH",
        "duration_seconds": 0,
        "reported_state": True,
        "voltage": {"min": 11, "max": 13},
    }
    threshold_payload = {
        "enabled": True,
        "lower_threshold": 6.5,
        "upper_threshold": 8.0,
        "below_risk_level": "HIGH",
        "above_risk_level": "HIGH",
        "delay_seconds": 0,
    }
    actuator_threshold_payload = {
        "enabled": True,
        "lower_threshold": 11,
        "upper_threshold": 13,
        "below_risk_level": "HIGH",
        "above_risk_level": "HIGH",
        "delay_seconds": 0,
    }

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            sensor_rule = await client.post(
                f"{base}/sensors/{sensor_public}/alert-scenarios",
                headers=owner_headers,
                json=scenario_payload,
            )
            actuator_rule = await client.post(
                f"{base}/actuators/{actuator_public}/alert-scenarios",
                headers=admin_headers,
                json=actuator_scenario_payload,
            )
            sensor_threshold = await client.post(
                f"{base}/sensors/{sensor_public}/threshold-alert",
                headers=owner_headers,
                json=threshold_payload,
            )
            actuator_threshold = await client.post(
                f"{base}/actuators/{actuator_public}/threshold-alerts/VOLTAGE",
                headers=admin_headers,
                json=actuator_threshold_payload,
            )
            assert sensor_rule.status_code == 201, sensor_rule.text
            assert actuator_rule.status_code == 201, actuator_rule.text
            assert sensor_threshold.status_code == 201, sensor_threshold.text
            assert actuator_threshold.status_code == 201, actuator_threshold.text
            sensor_rule_id = sensor_rule.json()["id"]
            actuator_rule_id = actuator_rule.json()["id"]

        async with AsyncSessionLocal() as db:
            db.add(
                ProjectScenario(
                    project_id=project.id,
                    device_id=device.id,
                    name=f"Managed {suffix}",
                    is_active=False,
                    created_by=admin.id,
                )
            )
            await db.commit()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            old_aggregate = await client.get(
                f"{base}/runtime-scenarios",
                headers=owner_headers,
            )
            assert old_aggregate.status_code == 404

            blocked = [
                await client.post(
                    f"{base}/sensors/{sensor_public}/alert-scenarios",
                    headers=owner_headers,
                    json=scenario_payload,
                ),
                await client.patch(
                    f"{base}/sensors/{sensor_public}/alert-scenarios/{sensor_rule_id}",
                    headers=owner_headers,
                    json={"name": "Blocked rename"},
                ),
                await client.delete(
                    f"{base}/sensors/{sensor_public}/alert-scenarios/{sensor_rule_id}",
                    headers=owner_headers,
                ),
                await client.post(
                    f"{base}/actuators/{actuator_public}/alert-scenarios",
                    headers=admin_headers,
                    json=actuator_scenario_payload,
                ),
                await client.patch(
                    f"{base}/actuators/{actuator_public}/alert-scenarios/{actuator_rule_id}",
                    headers=admin_headers,
                    json={"name": "Blocked rename"},
                ),
                await client.delete(
                    f"{base}/actuators/{actuator_public}/alert-scenarios/{actuator_rule_id}",
                    headers=admin_headers,
                ),
                await client.patch(
                    f"{base}/sensors/{sensor_public}/threshold-alert",
                    headers=owner_headers,
                    json={"upper_threshold": 7.5},
                ),
                await client.delete(
                    f"{base}/sensors/{sensor_public}/threshold-alert",
                    headers=owner_headers,
                ),
                await client.patch(
                    f"{base}/actuators/{actuator_public}/threshold-alerts/VOLTAGE",
                    headers=admin_headers,
                    json={"upper_threshold": 12.5},
                ),
                await client.delete(
                    f"{base}/actuators/{actuator_public}/threshold-alerts/VOLTAGE",
                    headers=admin_headers,
                ),
            ]
            assert all(response.status_code == 409 for response in blocked)
            assert all(
                response.json()["code"] == "PROJECT_SCENARIO_MANAGED"
                for response in blocked
            )
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(ProjectScenario).where(
                    ProjectScenario.device_id == device.id,
                    ProjectScenario.name == f"Managed {suffix}",
                )
            )
            if sensor_internal is not None:
                await db.execute(
                    delete(ThresholdAlertConfig).where(
                        ThresholdAlertConfig.sensor_id == sensor_internal
                    )
                )
            if actuator_internal is not None:
                await db.execute(
                    delete(ThresholdAlertConfig).where(
                        ThresholdAlertConfig.actuator_id == actuator_internal
                    )
                )
            rule_ids = [
                rule_id
                for rule_id in (sensor_rule_id, actuator_rule_id)
                if rule_id is not None
            ]
            if rule_ids:
                await db.execute(
                    delete(AlertRule).where(AlertRule.public_id.in_(rule_ids))
                )
            if sensor_internal is not None:
                await db.execute(delete(Sensor).where(Sensor.id == sensor_internal))
            if actuator_internal is not None:
                await db.execute(
                    delete(Actuator).where(Actuator.id == actuator_internal)
                )
            await db.commit()
