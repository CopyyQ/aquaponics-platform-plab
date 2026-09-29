from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.core.enums import UserRole
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.actuator import Actuator
from app.models.actuator_model import ActuatorModel
from app.models.device import Device
from app.models.project import Project
from app.models.user import User
from app.services.automatic_feeder_service import ensure_automatic_feeder_config
from tests.session_auth import session_headers


async def _make_feeder() -> tuple[dict[str, str], Project, Device, Actuator]:
    suffix = uuid4().hex[:8].upper()
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        model = await db.scalar(select(ActuatorModel).where(ActuatorModel.code == "AUTOMATIC_FEEDER"))
        assert admin and project and device and model
        sequence = int(
            await db.scalar(
                select(func.max(Actuator.sequence_number)).where(Actuator.device_id == device.id)
            )
            or 0
        ) + 1
        actuator = Actuator(
            device_id=device.id,
            actuator_model_id=model.id,
            sequence_number=sequence,
            code=f"FEEDER-{suffix}",
            name="Máy cho ăn tự động test",
            is_enabled=True,
            desired_state=False,
            reported_state=False,
        )
        db.add(actuator)
        await db.flush()
        await ensure_automatic_feeder_config(db, actuator=actuator)
        await db.commit()
        await db.refresh(actuator)
        headers = await session_headers(admin)
        return headers, project, device, actuator


async def _cleanup_actuator(actuator_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Actuator).where(Actuator.id == actuator_id))
        await db.commit()


@pytest.mark.asyncio
async def test_feeder_get_and_patch_round_trip() -> None:
    headers, project, device, actuator = await _make_feeder()
    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(base, headers=headers)
            assert response.status_code == 200, response.text
            feeder = response.json()["feeder"]
            assert feeder["feed_level"] == "LEVEL_1"
            assert feeder["free_output_value"] is None
            assert feeder["free_output_unit"] is None
            assert feeder["schedule_enabled"] is True
            assert feeder["schedule"] == ["00:00", "08:00", "16:00"]
            assert feeder["current_feed"] is None
            assert feeder["last_feed_at"] is None
            assert feeder["next_feed_at"] is not None

            patched = await client.patch(
                base,
                headers=headers,
                json={
                    "feeder": {
                        "feed_level": "LEVEL_2",
                        "schedule_enabled": True,
                        "schedule": ["06:30", "12:00", "18:30"],
                    }
                },
            )
            assert patched.status_code == 200, patched.text
            assert patched.json()["feeder"]["feed_level"] == "LEVEL_2"
            assert patched.json()["feeder"]["schedule"] == [
                "06:30",
                "12:00",
                "18:30",
            ]
    finally:
        await _cleanup_actuator(actuator.id)


def test_feeder_contract_is_exported_in_openapi() -> None:
    app.openapi_schema = None
    document = app.openapi()
    path = "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}"
    get_schema = document["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert get_schema["$ref"].endswith("/ActuatorRead")
    actuator_schema = document["components"]["schemas"]["ActuatorRead"]
    assert "feeder" in actuator_schema["properties"]
    update_schema = document["components"]["schemas"]["ActuatorUpdate"]
    assert "feeder" in update_schema["properties"]

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schedule",
    [
        ["00:00", "08:00"],
        ["00:00", "08:00", "16:00", "20:00"],
        ["08:00", "08:00", "16:00"],
        ["24:00", "08:00", "16:00"],
        ["00:00:00", "08:00", "16:00"],
    ],
)
async def test_feeder_patch_rejects_invalid_schedule(schedule: list[str]) -> None:
    headers, project, device, actuator = await _make_feeder()
    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.patch(
                base,
                headers=headers,
                json={"feeder": {"schedule": schedule}},
            )
            assert response.status_code == 422, response.text
    finally:
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_feeder_patch_requires_free_value_and_unit() -> None:
    headers, project, device, actuator = await _make_feeder()
    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            missing = await client.patch(
                base,
                headers=headers,
                json={"feeder": {"feed_level": "FREE"}},
            )
            assert missing.status_code == 422, missing.text

            incompatible = await client.patch(
                base,
                headers=headers,
                json={
                    "feeder": {
                        "feed_level": "LEVEL_2",
                        "free_output_value": 5,
                        "free_output_unit": "SECOND",
                    }
                },
            )
            assert incompatible.status_code == 422, incompatible.text

            valid = await client.patch(
                base,
                headers=headers,
                json={
                    "feeder": {
                        "feed_level": "FREE",
                        "free_output_value": 5,
                        "free_output_unit": "SECOND",
                    }
                },
            )
            assert valid.status_code == 200, valid.text
            assert valid.json()["feeder"]["feed_level"] == "FREE"
            assert valid.json()["feeder"]["free_output_value"] == 5
            assert valid.json()["feeder"]["free_output_unit"] == "SECOND"
    finally:
        await _cleanup_actuator(actuator.id)


async def _make_regular_actuator() -> tuple[dict[str, str], Project, Device, Actuator]:
    suffix = uuid4().hex[:8].upper()
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        model = await db.scalar(
            select(ActuatorModel).where(ActuatorModel.code == "FISH_TANK_PUMP")
        )
        assert admin and project and device and model
        sequence = int(
            await db.scalar(
                select(func.max(Actuator.sequence_number)).where(Actuator.device_id == device.id)
            )
            or 0
        ) + 1
        actuator = Actuator(
            device_id=device.id,
            actuator_model_id=model.id,
            sequence_number=sequence,
            code=f"PUMP-{suffix}",
            name="Pump feeder boundary test",
            is_enabled=True,
            desired_state=False,
            reported_state=False,
        )
        db.add(actuator)
        await db.commit()
        await db.refresh(actuator)
        headers = await session_headers(admin)
        return headers, project, device, actuator


@pytest.mark.asyncio
async def test_non_feeder_actuator_returns_null_and_rejects_feeder_patch() -> None:
    headers, project, device, actuator = await _make_regular_actuator()
    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(base, headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["feeder"] is None

            rejected = await client.patch(
                base,
                headers=headers,
                json={"feeder": {"schedule": ["00:00", "08:00", "16:00"]}},
            )
            assert rejected.status_code == 422, rejected.text
            assert rejected.json()["code"] == "AUTOMATIC_FEEDER_REQUIRED"
    finally:
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_feeder_patch_records_project_activity() -> None:
    from app.models.audit import AuditLog

    headers, project, device, actuator = await _make_feeder()
    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            patched = await client.patch(
                base,
                headers=headers,
                json={
                    "feeder": {
                        "feed_level": "LEVEL_3",
                        "schedule": ["05:30", "11:30", "17:30"],
                    }
                },
            )
            assert patched.status_code == 200, patched.text

        async with AsyncSessionLocal() as db:
            activity = await db.scalar(
                select(AuditLog)
                .where(
                    AuditLog.project_id == project.id,
                    AuditLog.entity_id == actuator.id,
                    AuditLog.action == "AUTOMATIC_FEEDER_UPDATED",
                )
                .order_by(AuditLog.id.desc())
            )
            assert activity is not None
            assert activity.new_data["changes"]["feed_level"] == {
                "before": "LEVEL_1",
                "after": "LEVEL_3",
            }
            assert activity.new_data["changes"]["schedule"] == {
                "before": ["00:00", "08:00", "16:00"],
                "after": ["05:30", "11:30", "17:30"],
            }
    finally:
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_created_feeder_persists_default_config() -> None:
    from app.models.automatic_feeder import AutomaticFeederConfig

    suffix = uuid4().hex[:8].upper()
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.system_role == UserRole.ADMIN))
        project = await db.scalar(select(Project).where(Project.code == "CODEX-TEST-RUNTIME"))
        device = await db.scalar(select(Device).where(Device.code == "CODEX-TEST-DEVICE"))
        model = await db.scalar(select(ActuatorModel).where(ActuatorModel.code == "AUTOMATIC_FEEDER"))
        assert admin and project and device and model
        headers = await session_headers(admin)
        model_id = model.id
        project_public_id = project.public_id
        device_public_id = device.public_id

    actuator_internal_id: int | None = None
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                f"/api/v1/aquaponics-systems/{project_public_id}/devices/{device_public_id}/actuators",
                headers=headers,
                json={
                    "actuator_model_id": model_id,
                    "code": f"AUTOFEED-{suffix}",
                    "name": "Máy cho ăn tự động API",
                },
            )
            assert created.status_code == 201, created.text
            assert created.json()["feeder"]["schedule"] == ["00:00", "08:00", "16:00"]
            actuator_public_id = created.json()["id"]

        async with AsyncSessionLocal() as db:
            actuator_internal_id = await db.scalar(
                select(Actuator.id).where(Actuator.public_id == actuator_public_id)
            )
            assert actuator_internal_id is not None
            config = await db.scalar(
                select(AutomaticFeederConfig).where(
                    AutomaticFeederConfig.actuator_id == actuator_internal_id
                )
            )
            assert config is not None
    finally:
        if actuator_internal_id is not None:
            await _cleanup_actuator(actuator_internal_id)


@pytest.mark.asyncio
async def test_feeder_fixed_level_clears_free_output_and_rejects_orphan_free_params() -> None:
    headers, project, device, actuator = await _make_feeder()
    base = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            orphan = await client.patch(
                base,
                headers=headers,
                json={
                    "feeder": {
                        "free_output_value": 5,
                        "free_output_unit": "SECOND",
                    }
                },
            )
            assert orphan.status_code == 422, orphan.text

            free = await client.patch(
                base,
                headers=headers,
                json={
                    "feeder": {
                        "feed_level": "FREE",
                        "free_output_value": 5,
                        "free_output_unit": "SECOND",
                    }
                },
            )
            assert free.status_code == 200, free.text

            fixed = await client.patch(
                base,
                headers=headers,
                json={"feeder": {"feed_level": "LEVEL_2"}},
            )
            assert fixed.status_code == 200, fixed.text
            assert fixed.json()["feeder"]["feed_level"] == "LEVEL_2"
            assert fixed.json()["feeder"]["free_output_value"] is None
            assert fixed.json()["feeder"]["free_output_unit"] is None
    finally:
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_feeder_read_derives_current_and_last_feed_runtime_state() -> None:
    from datetime import UTC, datetime, timedelta

    from app.models.automatic_feeder import AutomaticFeederEvent
    from app.services.automatic_feeder_service import get_automatic_feeder_read

    _headers, _project, _device, actuator = await _make_feeder()
    now = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)
    completed_at = now - timedelta(hours=2)
    started_at = now - timedelta(minutes=20)
    try:
        async with AsyncSessionLocal() as db:
            db.add_all(
                [
                    AutomaticFeederEvent(
                        actuator_id=actuator.id,
                        source="SCHEDULE",
                        feed_level="LEVEL_1",
                        scheduled_at=completed_at - timedelta(minutes=5),
                        started_at=completed_at - timedelta(minutes=4),
                        ended_at=completed_at,
                        status="COMPLETED",
                    ),
                    AutomaticFeederEvent(
                        actuator_id=actuator.id,
                        source="MANUAL",
                        feed_level="LEVEL_3",
                        scheduled_at=started_at - timedelta(minutes=1),
                        started_at=started_at,
                        status="RUNNING",
                    ),
                ]
            )
            await db.commit()
            row = await db.get(Actuator, actuator.id)
            assert row is not None
            feeder = await get_automatic_feeder_read(db, actuator=row, now=now)
            assert feeder is not None
            assert feeder["current_feed"]["status"] == "RUNNING"
            assert feeder["current_feed"]["source"] == "MANUAL"
            assert feeder["current_feed"]["feed_level"] == "LEVEL_3"
            assert feeder["current_feed"]["started_at"] == started_at
            assert feeder["last_feed_at"] == completed_at
    finally:
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_feeder_read_derives_next_feed_and_rolls_to_next_day() -> None:
    from datetime import UTC, datetime

    from app.schemas.automatic_feeder import AutomaticFeederUpdate
    from app.services.automatic_feeder_service import (
        get_automatic_feeder_read,
        update_automatic_feeder_config,
    )

    _headers, _project, _device, actuator = await _make_feeder()
    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(Actuator, actuator.id)
            assert row is not None
            await update_automatic_feeder_config(
                db,
                actuator=row,
                payload=AutomaticFeederUpdate(
                    schedule=["06:30", "12:00", "18:30"],
                    schedule_enabled=True,
                ),
            )
            await db.commit()

            same_day = await get_automatic_feeder_read(
                db,
                actuator=row,
                now=datetime(2026, 9, 28, 6, 0, tzinfo=UTC),  # 13:00 local
            )
            assert same_day is not None
            assert same_day["next_feed_at"] == datetime(
                2026, 9, 28, 11, 30, tzinfo=UTC
            )

            rollover = await get_automatic_feeder_read(
                db,
                actuator=row,
                now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),  # 19:00 local
            )
            assert rollover is not None
            assert rollover["next_feed_at"] == datetime(
                2026, 9, 28, 23, 30, tzinfo=UTC
            )

            await update_automatic_feeder_config(
                db,
                actuator=row,
                payload=AutomaticFeederUpdate(schedule_enabled=False),
            )
            disabled = await get_automatic_feeder_read(
                db,
                actuator=row,
                now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            )
            assert disabled is not None
            assert disabled["next_feed_at"] is None
    finally:
        await _cleanup_actuator(actuator.id)


def test_feeder_runtime_fields_are_exported_in_openapi() -> None:
    app.openapi_schema = None
    document = app.openapi()
    feeder = document["components"]["schemas"]["AutomaticFeederRead"]["properties"]
    assert "current_feed" in feeder
    assert "last_feed_at" in feeder
    assert "next_feed_at" in feeder
    assert feeder["last_feed_at"]["anyOf"][0]["format"] == "date-time"
    assert feeder["next_feed_at"]["anyOf"][0]["format"] == "date-time"


@pytest.mark.asyncio
async def test_list_actuators_returns_200_without_async_lazy_loading() -> None:
    headers, project, device, actuator = await _make_feeder()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}/actuators",
                headers=headers,
            )
            assert response.status_code == 200, response.text
            rows = response.json()
            assert any(row["id"] == str(actuator.public_id) for row in rows)
    finally:
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_list_sensors_returns_200_without_async_lazy_loading() -> None:
    headers, project, device, actuator = await _make_feeder()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}/sensors",
                headers=headers,
            )
            assert response.status_code == 200, response.text
    finally:
        await _cleanup_actuator(actuator.id)


@pytest.mark.asyncio
async def test_list_actuators_embeds_feeder_config_for_feeder_models() -> None:
    headers, project, device, actuator = await _make_feeder()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}/actuators",
                headers=headers,
            )
            assert response.status_code == 200, response.text
            row = next(
                item for item in response.json() if item["id"] == str(actuator.public_id)
            )
            feeder = row["feeder"]
            assert feeder is not None
            assert feeder["feed_level"] == "LEVEL_1"
            assert feeder["free_output_value"] is None
            assert feeder["free_output_unit"] is None
            assert feeder["schedule_enabled"] is True
            assert feeder["schedule"] == ["00:00", "08:00", "16:00"]
            assert feeder["current_feed"] is None
            assert feeder["last_feed_at"] is None
            assert feeder["next_feed_at"] is not None
    finally:
        await _cleanup_actuator(actuator.id)
