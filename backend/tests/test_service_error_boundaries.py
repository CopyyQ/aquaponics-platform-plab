from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.enums import UserStatus
from app.core.exceptions import ApplicationError
from app.services.alert_scenario_service import _condition
from app.services.project_device_config_service import export_project_device_config
from app.services.threshold_alert_config_service import (
    apply_threshold_alert_config_update,
)


@pytest.fixture(scope="session")
def disposable_runtime_fixture():
    yield


SERVICE_FILES = (
    "app/services/access_service.py",
    "app/services/project_lifecycle_service.py",
    "app/services/password_service.py",
    "app/services/threshold_alert_config_service.py",
    "app/services/alert_scenario_service.py",
    "app/services/credential_service.py",
    "app/services/device_auth_service.py",
    "app/services/mqtt_connection_config_service.py",
    "app/services/project_device_config_service.py",
)


def test_migrated_services_do_not_import_fastapi() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in SERVICE_FILES:
        text = (root / relative).read_text(encoding="utf-8")
        assert "from fastapi" not in text, relative
        assert "HTTPException" not in text, relative


def test_invalid_threshold_order_raises_domain_error() -> None:
    class Config:
        lower_threshold = 1.0
        upper_threshold = 2.0

    with pytest.raises(ApplicationError) as captured:
        apply_threshold_alert_config_update(
            Config(),
            {"lower_threshold": 3.0},
        )

    assert captured.value.code == "INVALID_THRESHOLD_RANGE"
    assert captured.value.status_code == 422


def test_sensor_scenario_requires_range_and_mode_as_domain_error() -> None:
    with pytest.raises(ApplicationError) as captured:
        _condition(
            "SENSOR",
            {
                "duration_seconds": 0,
                "range": None,
                "range_mode": None,
            },
        )

    assert captured.value.code == "INVALID_SENSOR_SCENARIO"
    assert captured.value.status_code == 422


@pytest.mark.asyncio
async def test_mqtt_export_invalid_public_host_raises_typed_error(
    monkeypatch,
) -> None:
    project = SimpleNamespace(id=17)
    owner = SimpleNamespace(
        status=UserStatus.ACTIVE,
        is_deleted=False,
        deleted_at=None,
    )

    class Result:
        def first(self):
            return project, owner

    class FakeDb:
        async def execute(self, _query):
            return Result()

    monkeypatch.setattr(
        settings,
        "mqtt_public_host",
        "127.0.0.1",
    )

    with pytest.raises(ApplicationError) as captured:
        await export_project_device_config(
            FakeDb(),
            project_id=project.id,
        )

    assert captured.value.code == "MQTT_PUBLIC_HOST_INVALID"
    assert captured.value.status_code == 500
