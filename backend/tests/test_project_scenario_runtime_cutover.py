from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.models.actuator import Actuator, ActuatorReading, ActuatorStateHistory
from app.models.actuator_model import ActuatorModel
from app.models.device import Device
from app.models.operational_alert import NotificationOutbox, OperationalIncident
from app.models.project import Project
from app.models.project_scenario import ProjectScenario, ProjectScenarioItem
from app.models.sensor import Sensor
from app.models.sensor_model import SensorModel
from app.models.telemetry import TelemetryReading
from app.models.user import User
from app.mqtt.handlers import handle_status
from app.schemas.telemetry import DeviceReadingInput, DeviceTelemetryInput
from app.services.telemetry_service import ingest_telemetry


async def _context(db):
    project = await db.scalar(
        select(Project).where(Project.code == "CODEX-TEST-RUNTIME")
    )
    admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
    device = await db.scalar(select(Device).where(Device.project_id == project.id))
    assert project is not None and admin is not None and device is not None
    return project, device, admin


async def _clear_scenarios(db, device_id: int) -> None:
    incident_ids = select(OperationalIncident.id).where(
        OperationalIncident.device_id == device_id,
        OperationalIncident.project_scenario_id.is_not(None),
    )
    await db.execute(
        delete(NotificationOutbox).where(
            NotificationOutbox.incident_id.in_(incident_ids)
        )
    )
    await db.execute(
        delete(OperationalIncident).where(
            OperationalIncident.device_id == device_id,
            OperationalIncident.project_scenario_id.is_not(None),
        )
    )
    await db.execute(
        delete(ProjectScenario).where(ProjectScenario.device_id == device_id)
    )
    await db.flush()


@pytest.mark.asyncio
async def test_sensor_telemetry_uses_project_scenario_engine_only_when_managed(
    monkeypatch,
) -> None:
    calls = {"new": 0, "legacy": 0}

    async def new_eval(*_args, **_kwargs):
        calls["new"] += 1
        return []

    async def legacy_eval(*_args, **_kwargs):
        calls["legacy"] += 1

    monkeypatch.setattr(
        "app.services.telemetry_service.evaluate_active_sensor_scenario",
        new_eval,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.telemetry_service.evaluate_sensor_threshold_incident",
        legacy_eval,
    )

    async with AsyncSessionLocal() as db:
        project, device, admin = await _context(db)
        await _clear_scenarios(db, device.id)
        model = await db.scalar(select(SensorModel).where(SensorModel.code == "PH"))
        assert model is not None
        suffix = uuid4().hex[:8]
        sensor = Sensor(
            device_id=device.id,
            sensor_model_id=model.id,
            code=f"CUTOVER-PH-{suffix}",
            name=f"Cutover pH {suffix}",
            is_enabled=True,
        )
        db.add(sensor)
        scenario = ProjectScenario(
            project_id=project.id,
            device_id=device.id,
            name="Cutover",
            is_active=True,
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(scenario)
        await db.flush()
        db.add(
            ProjectScenarioItem(
                project_scenario_id=scenario.id,
                target_type="SENSOR",
                sensor_id=sensor.id,
                actuator_id=None,
                name=sensor.name,
                is_enabled=True,
            )
        )
        await db.commit()
        now = datetime.now(UTC)
        result = await ingest_telemetry(
            db,
            device=device,
            payload=DeviceTelemetryInput(
                sent_at=now,
                readings=[
                    DeviceReadingInput(
                        sensor_code=sensor.code,
                        value=7.7,
                        recorded_at=now,
                    )
                ],
            ),
            received_at=now,
        )
        assert result.accepted == 1
        assert calls == {"new": 1, "legacy": 0}

        await db.execute(
            delete(TelemetryReading).where(TelemetryReading.sensor_id == sensor.id)
        )
        await db.execute(
            delete(ProjectScenario).where(ProjectScenario.device_id == device.id)
        )
        await db.execute(delete(Sensor).where(Sensor.id == sensor.id))
        await db.commit()


@pytest.mark.asyncio
async def test_mqtt_actuator_status_uses_project_scenario_engine_only_when_managed(
    monkeypatch,
) -> None:
    calls = {"new": 0, "legacy": 0}

    async def new_eval(*_args, **_kwargs):
        calls["new"] += 1
        return []

    async def legacy_eval(*_args, **_kwargs):
        calls["legacy"] += 1
        return []

    monkeypatch.setattr(
        "app.mqtt.handlers.evaluate_active_actuator_scenario",
        new_eval,
        raising=False,
    )
    monkeypatch.setattr(
        "app.mqtt.handlers.evaluate_alert_scenarios_for_actuator",
        legacy_eval,
    )

    actuator_id = None
    async with AsyncSessionLocal() as db:
        project, device, admin = await _context(db)
        await _clear_scenarios(db, device.id)
        model = await db.scalar(
            select(ActuatorModel).where(ActuatorModel.is_active.is_(True))
        )
        assert model is not None
        sequence = (
            await db.scalar(
                select(Actuator.sequence_number)
                .where(Actuator.device_id == device.id)
                .order_by(Actuator.sequence_number.desc())
                .limit(1)
            )
            or 0
        ) + 100
        suffix = uuid4().hex[:8].upper()
        actuator = Actuator(
            device_id=device.id,
            actuator_model_id=model.id,
            sequence_number=sequence,
            code=f"CUTOVER-{suffix}",
            name=f"Cutover actuator {suffix}",
            is_enabled=True,
            desired_state=True,
            reported_state=False,
        )
        db.add(actuator)
        scenario = ProjectScenario(
            project_id=project.id,
            device_id=device.id,
            name="Cutover actuator",
            is_active=True,
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(scenario)
        await db.flush()
        db.add(
            ProjectScenarioItem(
                project_scenario_id=scenario.id,
                target_type="ACTUATOR",
                sensor_id=None,
                actuator_id=actuator.id,
                name=actuator.name,
                is_enabled=True,
            )
        )
        await db.commit()
        actuator_id = actuator.id
        device_code = device.code
        actuator_code = actuator.code

    now = datetime.now(UTC)
    await handle_status(
        device_code,
        json.dumps(
            {
                "status": "ONLINE",
                "sent_at": now.isoformat(),
                "actuators": [
                    {
                        "actuator_code": actuator_code,
                        "state": True,
                        "voltage_v": 12.0,
                        "current_a": 1.0,
                        "recorded_at": now.isoformat(),
                    }
                ],
            }
        ).encode(),
    )
    assert calls == {"new": 1, "legacy": 0}

    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ActuatorReading).where(ActuatorReading.actuator_id == actuator_id)
        )
        await db.execute(
            delete(ActuatorStateHistory).where(
                ActuatorStateHistory.actuator_id == actuator_id
            )
        )
        await db.execute(
            delete(ProjectScenario).where(ProjectScenario.device_id == device.id)
        )
        await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
        await db.commit()
