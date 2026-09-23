from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.project_overview import ActuatorActiveAlertRead
from app.services.monitoring_service import _actuator_electrical_payload


def _row(**overrides):
    now = datetime.now(UTC)
    data = {
        "voltage_v": 0.0,
        "current_a": 0.0,
        "electrical_recorded_at": now,
        "electrical_received_at": now,
        "voltage_lower_threshold": None,
        "voltage_upper_threshold": None,
        "current_lower_threshold": None,
        "current_upper_threshold": None,
        "minimum_running_current_a": None,
        "maximum_running_current_a": None,
        "incident_id": 4,
        "incident_severity": "WARNING",
        "incident_risk": "MEDIUM",
        "incident_status": "OPEN",
        "incident_started_at": now,
        "incident_trigger_snapshot": {
            "branch_name": "Bơm bể cá - Không có nguồn động lực",
            "evaluator_type": "MULTI_CONDITION",
            "message": "Bơm đang được bật nhưng điện áp và dòng điện đều khoảng 0.",
        },
        "incident_rule_name": None,
        "incident_evaluator_type": None,
    }
    data.update(overrides)
    return SimpleNamespace(_mapping=data)


def test_project_scenario_actuator_incident_uses_snapshot_metadata_when_rule_is_absent():
    payload = _actuator_electrical_payload([_row()], datetime.now(UTC))
    alert = payload["active_incident"]

    assert alert is not None
    assert alert["rule_name"] == "Bơm bể cá - Không có nguồn động lực"
    assert alert["evaluator_type"] == "MULTI_CONDITION"
    ActuatorActiveAlertRead.model_validate(alert)
