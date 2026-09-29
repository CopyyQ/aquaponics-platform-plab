from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.actuator import ActuatorCommand
from app.schemas.actuator import ActuatorCommandCreate
from tests.test_automatic_feeder_api import (
    _cleanup_actuator,
    _make_feeder,
    _make_regular_actuator,
)


async def _cleanup_with_commands(actuator_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ActuatorCommand).where(ActuatorCommand.actuator_id == actuator_id))
        await db.commit()
    await _cleanup_actuator(actuator_id)


@pytest.mark.asyncio
async def test_manual_feed_command_snapshots_current_config() -> None:
    headers, project, device, actuator = await _make_feeder()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers, json={"command_type": "FEED"})
            assert response.status_code == 202, response.text
            payload = response.json()
            assert payload["command_type"] == "FEED"
            assert payload["desired_state"] is True
            assert payload["params"] == {
                "feed_level": "LEVEL_1",
                "free_output_value": None,
                "free_output_unit": None,
            }

        async with AsyncSessionLocal() as db:
            command = await db.get(ActuatorCommand, payload["command_id"])
            assert command is not None
            assert command.command_type == "FEED"
            assert command.command_payload == payload["params"]
    finally:
        await _cleanup_with_commands(actuator.id)


@pytest.mark.asyncio
async def test_non_feeder_rejects_feed_command() -> None:
    headers, project, device, actuator = await _make_regular_actuator()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers, json={"command_type": "FEED"})
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "AUTOMATIC_FEEDER_REQUIRED"
            assert response.json()["detail"] == "Actuator này không phải máy cho ăn tự động."
    finally:
        await _cleanup_with_commands(actuator.id)


@pytest.mark.asyncio
async def test_legacy_set_state_command_stays_compatible() -> None:
    headers, project, device, actuator = await _make_regular_actuator()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(url, headers=headers, json={"desired_state": True})
            assert response.status_code == 202, response.text
            payload = response.json()
            assert payload["command_type"] == "SET_STATE"
            assert payload["desired_state"] is True
            assert payload["params"] == {}
    finally:
        await _cleanup_with_commands(actuator.id)


def test_feed_command_contract_is_exported_in_openapi() -> None:
    app.openapi_schema = None
    document = app.openapi()
    create_schema = document["components"]["schemas"]["ActuatorCommandCreate"]
    read_schema = document["components"]["schemas"]["ActuatorCommandRead"]
    assert "command_type" in create_schema["properties"]
    assert "params" in create_schema["properties"]
    assert "command_type" in read_schema["properties"]
    assert "params" in read_schema["properties"]

@pytest.mark.asyncio
async def test_free_feed_command_requires_free_output_with_vietnamese_error() -> None:
    headers, project, device, actuator = await _make_feeder()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                url,
                headers=headers,
                json={"command_type": "FEED", "params": {"feed_level": "FREE"}},
            )
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "AUTOMATIC_FEEDER_FREE_OUTPUT_REQUIRED"
            assert (
                response.json()["detail"]
                == "Mức FREE yêu cầu free_output_value và free_output_unit."
            )
    finally:
        await _cleanup_with_commands(actuator.id)

@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"command_type": "SET_STATE"}, "SET_STATE yêu cầu desired_state"),
        (
            {"command_type": "SET_STATE", "desired_state": True, "params": {}},
            "SET_STATE không nhận params",
        ),
        (
            {"command_type": "FEED", "desired_state": False},
            "FEED không cho phép desired_state=false",
        ),
    ],
)
def test_command_validation_messages_are_valid_vietnamese(
    payload: dict, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        ActuatorCommandCreate.model_validate(payload)

@pytest.mark.asyncio
async def test_feed_command_override_rejects_orphan_free_params_and_accepts_free_level() -> None:
    headers, project, device, actuator = await _make_feeder()
    url = (
        f"/api/v1/aquaponics-systems/{project.public_id}/devices/{device.public_id}"
        f"/actuators/{actuator.public_id}/commands"
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            invalid = await client.post(
                url,
                headers=headers,
                json={
                    "command_type": "FEED",
                    "params": {
                        "free_output_value": 5,
                        "free_output_unit": "SECOND",
                    },
                },
            )
            assert invalid.status_code == 422, invalid.text
            assert invalid.json()["code"] == "AUTOMATIC_FEEDER_FREE_OUTPUT_INVALID"

            valid = await client.post(
                url,
                headers=headers,
                json={
                    "command_type": "FEED",
                    "params": {
                        "feed_level": "FREE",
                        "free_output_value": 5,
                        "free_output_unit": "SECOND",
                    },
                },
            )
            assert valid.status_code == 202, valid.text
            assert valid.json()["params"] == {
                "feed_level": "FREE",
                "free_output_value": 5,
                "free_output_unit": "SECOND",
            }
    finally:
        await _cleanup_with_commands(actuator.id)
