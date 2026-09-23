"""Regression gates for the final canonical 0050 HTTP contract."""

from collections import Counter

from fastapi.testclient import TestClient

from app.main import app


def _openapi() -> dict:
    return app.openapi()


def test_alert_contract_supports_sensor_and_actuator_sources() -> None:
    schemas = _openapi()["components"]["schemas"]
    assert schemas["AlertResourceType"]["enum"] == ["SENSOR", "ACTUATOR"]
    properties = schemas["AlertRead"]["properties"]
    assert {"sensor_id", "actuator_id", "device_id", "resource_type"} <= properties.keys()


def test_static_alert_settings_route_precedes_dynamic_alert_detail() -> None:
    response = TestClient(app).get("/api/v1/aquaponics-systems/1/alerts/settings")
    assert response.status_code == 401


def test_alert_contract_preserves_threshold_snapshot() -> None:
    properties = _openapi()["components"]["schemas"]["AlertRead"]["properties"]
    assert {"metric", "direction", "actual_value", "threshold_value", "risk_level", "message"} <= properties.keys()


def test_actuator_voltage_and_current_metrics_are_typed() -> None:
    schema = _openapi()["components"]["schemas"]["ActuatorThresholdMetric"]
    assert schema["enum"] == ["VOLTAGE", "CURRENT"]
    paths = _openapi()["paths"]
    route = "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/threshold-alerts/{metric}"
    assert all(any(p["name"] == "metric" and "$ref" in p["schema"] for p in paths[route][method]["parameters"]) for method in ("get", "post", "patch", "delete"))


def test_mqtt_export_has_no_threshold_owner_or_summary_leakage() -> None:
    schemas = _openapi()["components"]["schemas"]
    assert not ({"lower_threshold", "upper_threshold"} & schemas["DeviceConfigSensor"]["properties"].keys())
    export = schemas["AquaponicsSystemMqttConfigExport"]["properties"]
    assert "summary" not in export
    assert "owner" not in schemas["DeviceConfigAquaponicsSystem"]["properties"]
    topics = schemas["DeviceConfigTopics"]["properties"]
    assert {"telemetry", "status", "commands", "command_ack"} <= topics.keys()
    assert "command" not in topics
    actuator = schemas["DeviceConfigActuator"]["properties"]
    assert "control" in actuator


def test_mqtt_export_is_single_and_supports_mixed_devices() -> None:
    paths = _openapi()["paths"]
    exports = [(path, method) for path, item in paths.items() for method in item if "mqtt-config" in path]
    assert exports == [("/api/v1/aquaponics-systems/{system_id}/mqtt-config/export", "get")]
    device = _openapi()["components"]["schemas"]["DeviceConfigDevice"]["properties"]
    assert {"sensors", "actuators"} <= device.keys()


def test_template_slot_detail_gets_and_separate_inputs_exist() -> None:
    paths = _openapi()["paths"]
    base = "/api/v1/device-templates/{template_id}"
    assert "get" in paths[f"{base}/sensors/{{mapping_id}}"]
    assert "get" in paths[f"{base}/actuators/{{mapping_id}}"]
    schemas = _openapi()["components"]["schemas"]
    assert "actuator_model_id" not in schemas["TemplateSensorSlotCreate"]["properties"]
    assert "sensor_model_id" not in schemas["TemplateActuatorSlotCreate"]["properties"]
    for name in (
        "TemplateSensorSlotCreate", "TemplateSensorSlotUpdate", "TemplateSensorSlotRead",
        "TemplateActuatorSlotCreate", "TemplateActuatorSlotUpdate", "TemplateActuatorSlotRead",
    ):
        properties = schemas[name]["properties"]
        assert "code" in properties
        assert "slot" + "_code" not in properties


def test_runtime_resource_responses_are_typed() -> None:
    schemas = _openapi()["components"]["schemas"]
    for name in ("DeviceRead", "SensorRead", "ActuatorRead", "TelemetryReadingRead", "MonitoringLatestRead", "MonitoringSeriesRead"):
        assert schemas[name].get("properties"), name
        assert schemas[name].get("additionalProperties") is not True


def test_canonical_mutations_reject_unknown_fields() -> None:
    schemas = _openapi()["components"]["schemas"]
    for name in ("AquaponicsSystemUpdate", "DeviceUpdate", "SensorUpdate", "ActuatorUpdate", "TemplateSensorSlotCreate", "TemplateActuatorSlotCreate"):
        assert schemas[name].get("additionalProperties") is False, name


def test_no_legacy_public_names_or_fields() -> None:
    document = _openapi()
    serialized = str(document)
    for term in ("Project", "project_id", "system_role", "/admin", "/projects", "overview", "device_kind", "feedback_role"):
        assert term not in serialized


def test_scada_runtime_uses_canonical_system_and_generic_alerts() -> None:
    schemas = _openapi()["components"]["schemas"]
    assert "aquaponics_system" in schemas["ScadaRuntimeResponse"]["properties"]
    assert "project" not in schemas["ScadaRuntimeResponse"]["properties"]
    assert {"resource_type", "sensor_id", "actuator_id"} <= schemas["ScadaRuntimeAlert"]["properties"].keys()


def test_no_free_form_canonical_contracts() -> None:
    schemas = _openapi()["components"]["schemas"]
    assert [name for name, schema in schemas.items() if schema.get("additionalProperties") is True] == []


def test_no_duplicate_operation_ids_or_writer_families() -> None:
    operations = [operation for item in _openapi()["paths"].values() for method, operation in item.items() if method in {"get", "post", "put", "patch", "delete"}]
    counts = Counter(operation["operationId"] for operation in operations)
    assert not [operation_id for operation_id, count in counts.items() if count > 1]


def test_public_monitoring_routes_are_not_exposed() -> None:
    paths = _openapi()["paths"]
    assert not [path for path in paths if "/public/" in path or "public-monitoring" in path]


def test_aquaponics_system_cannot_be_deleted() -> None:
    item = _openapi()["paths"]["/api/v1/aquaponics-systems/{system_id}"]
    assert "delete" not in item


def test_api_error_schema_is_canonical() -> None:
    schema = _openapi()["components"]["schemas"]["ApiErrorResponse"]
    assert {"code", "detail"} <= schema["properties"].keys()
    assert {"errors", "request_id"} <= schema["properties"].keys()


def test_protected_operations_document_auth_validation_and_server_errors() -> None:
    operation = _openapi()["paths"]["/api/v1/aquaponics-systems"]["get"]
    assert {"401", "403", "422", "500"} <= operation["responses"].keys()


def test_resource_routes_document_404() -> None:
    operation = _openapi()["paths"][
        "/api/v1/aquaponics-systems/{system_id}"
    ]["get"]
    assert "404" in operation["responses"]
    ref = operation["responses"]["404"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert ref.endswith("/ApiErrorResponse")


def test_mutations_document_conflict_and_create_system_documents_503() -> None:
    create_system = _openapi()["paths"]["/api/v1/aquaponics-systems"]["post"]
    assert "409" in create_system["responses"]
    assert "503" in create_system["responses"]
    change_password = _openapi()["paths"]["/api/v1/auth/change-password"]["post"]
    assert "400" in change_password["responses"]


def test_all_documented_api_errors_reference_canonical_schema() -> None:
    document = _openapi()
    methods = {"get", "post", "put", "patch", "delete"}
    error_statuses = {"400", "401", "403", "404", "409", "422", "500", "503"}
    violations: list[str] = []

    for path, path_item in document["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method, operation in path_item.items():
            if method not in methods:
                continue
            for status_code, response in operation.get("responses", {}).items():
                if status_code not in error_statuses:
                    continue
                schema = (
                    response.get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
                )
                if schema.get("$ref") != "#/components/schemas/ApiErrorResponse":
                    violations.append(
                        f"{method.upper()} {path} {status_code}: {schema}"
                    )

    assert violations == []
