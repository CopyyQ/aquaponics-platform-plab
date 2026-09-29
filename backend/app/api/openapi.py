from copy import deepcopy

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
CONFLICT_OPERATIONS = {
    ("get", "/api/v1/aquaponics-systems/{system_id}/mqtt-config/export"),
    ("post", "/api/v1/aquaponics-systems"),
    ("post", "/api/v1/users/{user_id}/aquaponics-systems"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/members"),
    ("delete", "/api/v1/aquaponics-systems/{system_id}/members/{user_id}"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/scada/layout/publish"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/lifecycle/disable"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/lifecycle/activate"),
    ("put", "/api/v1/aquaponics-systems/{system_id}/owner"),
    ("post", "/api/v1/users"),
    ("post", "/api/v1/users/{user_id}/disable"),
    ("post", "/api/v1/users/{user_id}/lock"),
    ("post", "/api/v1/users/{user_id}/soft-delete"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/alert-delivery/recipients"),
    ("patch", "/api/v1/aquaponics-systems/{system_id}/alert-delivery/recipients/{recipient_id}"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/alert-delivery/recipients/{recipient_id}/test"),
    ("post", "/api/v1/permissions"),
    ("post", "/api/v1/roles"),
    ("patch", "/api/v1/roles/{role_id}"),
    ("delete", "/api/v1/roles/{role_id}"),
    ("post", "/api/v1/role-assignments"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors/{sensor_id}/threshold-alert"),
    ("patch", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors/{sensor_id}/threshold-alert"),
    ("delete", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors/{sensor_id}/threshold-alert"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors/{sensor_id}/alert-scenarios"),
    ("patch", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors/{sensor_id}/alert-scenarios/{scenario_id}"),
    ("delete", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/sensors/{sensor_id}/alert-scenarios/{scenario_id}"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/threshold-alerts/{metric}"),
    ("patch", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/threshold-alerts/{metric}"),
    ("delete", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/threshold-alerts/{metric}"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/alert-scenarios"),
    ("patch", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/alert-scenarios/{scenario_id}"),
    ("delete", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/alert-scenarios/{scenario_id}"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/alerts/{alert_id}/acknowledge"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/alerts/{alert_id}/resolve"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/scenarios"),
    ("get", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/scenarios/{scenario_id}"),
    ("patch", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/scenarios/{scenario_id}"),
    ("delete", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/scenarios/{scenario_id}"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/scenarios/{scenario_id}/clone"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/scenarios/{scenario_id}/activate"),
    ("patch", "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/scenarios/{scenario_id}/items/{item_id}"),
    ("post", "/api/v1/sensor-models"),
    ("delete", "/api/v1/sensor-models/{model_id}"),
    ("post", "/api/v1/scenario-catalogs"),
    ("post", "/api/v1/device-templates"),
    ("post", "/api/v1/actuator-models"),
}
NOT_FOUND_EXEMPT_OPERATIONS = {
    ("delete", "/api/v1/roles/{role_id}/permissions/{permission_id}"),
}

SERVICE_UNAVAILABLE_OPERATIONS = {
    ("post", "/api/v1/aquaponics-systems"),
    ("post", "/api/v1/users/{user_id}/aquaponics-systems"),
    ("post", "/api/v1/aquaponics-systems/{system_id}/alert-delivery/recipients/{recipient_id}/test"),
}



def install_openapi_error_contract(app: FastAPI) -> None:
    def custom_openapi() -> dict:
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        for path, path_item in schema.get("paths", {}).items():
            if not path.startswith("/api/v1/"):
                continue

            for method, operation in path_item.items():
                if method not in HTTP_METHODS:
                    continue

                responses = operation.setdefault("responses", {})
                template = deepcopy(responses["500"])

                def add(status_code: str, description: str) -> None:
                    if status_code not in responses:
                        response = deepcopy(template)
                        response["description"] = description
                        responses[status_code] = response
                        return

                    response = responses[status_code]
                    response.setdefault("description", description)
                    template_json = (
                        template.get("content", {})
                        .get("application/json")
                    )
                    if template_json is not None:
                        response.setdefault("content", {})["application/json"] = (
                            deepcopy(template_json)
                        )

                if (
                    ("_id}" in path and (method, path) not in NOT_FOUND_EXEMPT_OPERATIONS)
                    or (method, path) == ("post", "/api/v1/role-assignments")
                ):
                    add("404", "Requested resource was not found")
                if (method, path) in CONFLICT_OPERATIONS:
                    add("409", "Request conflicts with current resource state")
                if path == "/api/v1/auth/change-password":
                    add("400", "Request cannot be applied")
                if (
                    path == "/api/v1/aquaponics-systems"
                    and method == "post"
                ):
                    add("404", "Selected bootstrap resource was not found")
                if (method, path) in SERVICE_UNAVAILABLE_OPERATIONS:
                    add("503", "Service temporarily unavailable")
                if path == "/api/v1/auth/login":
                    add("403", "Authentication request origin is not allowed")
                    add("429", "Too many login attempts")
                if path in {"/api/v1/auth/refresh", "/api/v1/auth/logout"}:
                    add("401", "Authentication session is invalid or expired")
                    add("403", "Authentication request origin is not allowed")

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
