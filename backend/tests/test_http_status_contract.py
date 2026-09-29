import ast
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.error_handlers import register_error_handlers
from app.main import app


@pytest.fixture(scope="session")
def disposable_runtime_fixture():
    yield


def _openapi() -> dict:
    app.openapi_schema = None
    return app.openapi()


def _literal_status(call: ast.Call) -> int | None:
    func = call.func
    name = (
        func.id
        if isinstance(func, ast.Name)
        else func.attr
        if isinstance(func, ast.Attribute)
        else ""
    )
    if name == "HTTPException":
        if (
            call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, int)
        ):
            return call.args[0].value
        for keyword in call.keywords:
            if (
                keyword.arg == "status_code"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, int)
            ):
                return keyword.value.value
    if name == "ApplicationError":
        if (
            len(call.args) >= 3
            and isinstance(call.args[2], ast.Constant)
            and isinstance(call.args[2].value, int)
        ):
            return call.args[2].value
        for keyword in call.keywords:
            if (
                keyword.arg == "status_code"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, int)
            ):
                return keyword.value.value
    return None


def _router_prefix(tree: ast.Module) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "router" for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        for keyword in node.value.keywords:
            if (
                keyword.arg == "prefix"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                return keyword.value.value
    return ""


def test_openapi_documents_every_direct_route_error_status() -> None:
    document = _openapi()
    api_root = Path(__file__).resolve().parents[1] / "app" / "api" / "v1"
    violations: list[str] = []

    for source_path in api_root.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        prefix = _router_prefix(tree)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            routes: list[tuple[str, str]] = []
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(
                    decorator.func, ast.Attribute
                ):
                    continue
                method = decorator.func.attr
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                    continue
                route = decorator.args[0].value
                if isinstance(route, str):
                    routes.append((method, f"/api/v1{prefix}{route}"))

            direct_statuses = {
                status_code
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and (status_code := _literal_status(child)) is not None
            }
            for method, path in routes:
                documented = document["paths"][path][method]["responses"]
                for status_code in sorted(direct_statuses):
                    if str(status_code) not in documented:
                        violations.append(f"{method.upper()} {path} missing {status_code}")

    assert violations == []


def test_async_actuator_command_returns_202_accepted() -> None:
    operation = _openapi()["paths"][
        "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/commands"
    ]["post"]
    assert "202" in operation["responses"]
    assert "201" not in operation["responses"]
    assert "409" not in operation["responses"]


def test_auth_operations_do_not_advertise_conflict_when_they_never_return_it() -> None:
    document = _openapi()
    operations = (
        ("/api/v1/auth/login", "post"),
        ("/api/v1/auth/refresh", "post"),
        ("/api/v1/auth/logout", "post"),
        ("/api/v1/auth/change-password", "post"),
        ("/api/v1/auth/me", "patch"),
    )
    violations = [
        f"{method.upper()} {path}"
        for path, method in operations
        if "409" in document["paths"][path][method]["responses"]
    ]
    assert violations == []


def test_plain_429_uses_canonical_too_many_requests_error_code() -> None:
    test_app = FastAPI()
    register_error_handlers(test_app)

    @test_app.get("/limited")
    async def limited() -> None:
        raise HTTPException(429, "Thu lai sau")

    response = TestClient(test_app).get("/limited")
    assert response.status_code == 429
    assert response.json() == {
        "code": "TOO_MANY_REQUESTS",
        "detail": "Thu lai sau",
    }


def test_mqtt_export_documents_service_conflict_status() -> None:
    operation = _openapi()["paths"]["/api/v1/aquaponics-systems/{system_id}/mqtt-config/export"][
        "get"
    ]
    assert "409" in operation["responses"]
    schema = operation["responses"]["409"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/ApiErrorResponse"


def test_non_conflicting_mutations_do_not_advertise_409() -> None:
    document = _openapi()
    operations = (
        ("patch", "/api/v1/scenario-catalogs/{catalog_id}"),
        ("put", "/api/v1/aquaponics-systems/{system_id}/alerts/settings"),
        ("patch", "/api/v1/aquaponics-systems/{system_id}/members/{user_id}"),
        ("post", "/api/v1/roles/{role_id}/permissions/{permission_id}"),
        ("patch", "/api/v1/users/{user_id}"),
        ("post", "/api/v1/users/{user_id}/force-logout"),
        (
            "post",
            "/api/v1/aquaponics-systems/{system_id}/devices/{device_id}/actuators/{actuator_id}/commands",
        ),
    )
    violations = [
        f"{method.upper()} {path}"
        for method, path in operations
        if "409" in document["paths"][path][method]["responses"]
    ]
    assert violations == []


def test_create_system_for_user_documents_503_generation_failure() -> None:
    operation = _openapi()["paths"]["/api/v1/users/{user_id}/aquaponics-systems"]["post"]
    assert "503" in operation["responses"]
    schema = operation["responses"]["503"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/ApiErrorResponse"



def test_role_assignment_documents_payload_reference_404() -> None:
    operation = _openapi()["paths"]["/api/v1/role-assignments"]["post"]
    assert "404" in operation["responses"]
    schema = operation["responses"]["404"]["content"]["application/json"]["schema"]
    assert schema["$ref"] == "#/components/schemas/ApiErrorResponse"


def test_idempotent_role_permission_delete_does_not_advertise_404() -> None:
    operation = _openapi()["paths"][
        "/api/v1/roles/{role_id}/permissions/{permission_id}"
    ]["delete"]
    assert "404" not in operation["responses"]


def test_swagger_and_openapi_endpoints_are_available() -> None:
    client = TestClient(app)
    docs = client.get("/docs")
    schema = client.get("/openapi.json")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    assert schema.status_code == 200
    assert schema.json() == _openapi()
