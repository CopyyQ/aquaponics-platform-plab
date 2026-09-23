import ast
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.api import deps as api_deps
from app.api.error_handlers import register_error_handlers
from app.api.v1.canonical_catalogs import _scenario_item_read
from app.core.exceptions import ApplicationError, ErrorDetail, InternalInvariantError
from app.main import app as real_app
from app.schemas.error import ApiErrorResponse, ApiValidationIssue


@pytest.fixture(scope="session")
def disposable_runtime_fixture():
    yield


def test_app_error_keeps_stable_code_status_and_details() -> None:
    issue = ErrorDetail(
        field="body.device_template_id",
        message="Giá trị không hợp lệ",
        type="greater_than",
    )
    error = ApplicationError(
        "VALIDATION_ERROR",
        "Dữ liệu gửi lên không hợp lệ.",
        422,
        (issue,),
    )

    assert error.code == "VALIDATION_ERROR"
    assert error.message == "Dữ liệu gửi lên không hợp lệ."
    assert error.status_code == 422
    assert error.errors == (issue,)


def test_internal_invariant_error_is_safe_500() -> None:
    error = InternalInvariantError(
        "SCENARIO_CATALOG_ITEM_CORRUPT",
        "Scenario catalog item is missing its target model",
    )
    assert error.status_code == 500
    assert error.code == "SCENARIO_CATALOG_ITEM_CORRUPT"
    assert error.expose_message is False


def test_api_error_response_omits_optional_fields_when_absent() -> None:
    payload = ApiErrorResponse(
        code="RESOURCE_NOT_FOUND",
        detail="Không tìm thấy tài nguyên yêu cầu.",
    )
    assert payload.model_dump(exclude_none=True) == {
        "code": "RESOURCE_NOT_FOUND",
        "detail": "Không tìm thấy tài nguyên yêu cầu.",
    }


def test_validation_issue_is_strict_and_typed() -> None:
    issue = ApiValidationIssue(
        field="body.device_template_id",
        message="Giá trị không hợp lệ",
        type="greater_than",
    )
    assert issue.model_dump() == {
        "field": "body.device_template_id",
        "message": "Giá trị không hợp lệ",
        "type": "greater_than",
    }


def _error_test_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    class Payload(BaseModel):
        count: int = Field(gt=0)

    @app.get("/domain")
    async def domain():
        raise ApplicationError(
            "DEVICE_NOT_FOUND",
            "Không tìm thấy thiết bị.",
            404,
        )

    @app.get("/legacy")
    async def legacy():
        raise HTTPException(
            409,
            {
                "code": "SCENARIO_CATALOG_MANAGED",
                "detail": "Kịch bản được quản lý tập trung.",
            },
        )

    @app.post("/validation")
    async def validation(payload: Payload):
        return payload

    @app.get("/invariant")
    async def invariant():
        raise InternalInvariantError(
            "SCENARIO_CATALOG_ITEM_CORRUPT",
            "Scenario catalog item is missing its target model",
        )

    @app.get("/header-error")
    async def header_error():
        raise HTTPException(
            429,
            "Thử lại sau.",
            headers={"Retry-After": "60"},
        )

    @app.get("/boom")
    async def boom():
        raise RuntimeError("database-password=must-not-leak")

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_is_top_level_canonical_json() -> None:
    response = _error_test_client().get("/domain")
    assert response.status_code == 404
    assert response.json() == {
        "code": "DEVICE_NOT_FOUND",
        "detail": "Không tìm thấy thiết bị.",
    }


def test_legacy_nested_http_exception_is_flattened() -> None:
    response = _error_test_client().get("/legacy")
    assert response.status_code == 409
    assert response.json() == {
        "code": "SCENARIO_CATALOG_MANAGED",
        "detail": "Kịch bản được quản lý tập trung.",
    }


def test_request_validation_is_normalized_without_input_echo() -> None:
    response = _error_test_client().post("/validation", json={"count": 0})
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"] == "Dữ liệu gửi lên không hợp lệ."
    assert body["errors"][0]["field"] == "body.count"
    assert "input" not in str(body)


def test_internal_invariant_error_masks_internal_message() -> None:
    response = _error_test_client().get("/invariant")
    body = response.json()
    assert response.status_code == 500
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    assert body["detail"] == (
        "Hệ thống gặp lỗi khi xử lý yêu cầu. Vui lòng thử lại sau."
    )
    assert "target model" not in response.text


def test_unhandled_exception_returns_safe_500(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="app.api.error_handlers")

    response = _error_test_client().get("/boom")
    body = response.json()

    assert response.status_code == 500
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    assert body["detail"] == (
        "Hệ thống gặp lỗi khi xử lý yêu cầu. Vui lòng thử lại sau."
    )
    assert body["request_id"]
    assert "database-password" not in response.text
    assert "database-password=must-not-leak" not in caplog.text


def test_unknown_route_uses_canonical_404() -> None:
    response = _error_test_client().get("/missing")
    assert response.status_code == 404
    assert response.json() == {
        "code": "RESOURCE_NOT_FOUND",
        "detail": "Không tìm thấy tài nguyên yêu cầu.",
    }


def test_missing_bearer_token_is_canonical_401() -> None:
    response = TestClient(real_app).get("/api/v1/auth/session")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "detail": "Chưa đăng nhập.",
    }


def test_invalid_path_uuid_is_json_error_not_nested_detail() -> None:
    response = TestClient(real_app).get(
        "/api/v1/aquaponics-systems/not-a-uuid"
    )
    assert response.status_code in {401, 422}
    body = response.json()
    assert isinstance(body.get("code"), str)
    assert isinstance(body.get("detail"), str)


def test_auth_dependencies_no_longer_define_transport_specific_error() -> None:
    assert not hasattr(api_deps, "AccountAuthError")


def test_scenario_item_missing_target_model_raises_typed_internal_error() -> None:
    row = SimpleNamespace(
        target_type="SENSOR",
        sensor_model=None,
        actuator_model=None,
    )
    with pytest.raises(InternalInvariantError) as captured:
        _scenario_item_read(row)
    assert captured.value.code == "SCENARIO_CATALOG_ITEM_CORRUPT"


def test_router_http_exception_dict_details_have_code_and_detail_strings() -> None:
    api_root = Path(__file__).resolve().parents[1] / "app" / "api"
    violations: list[str] = []

    for path in api_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_http_exception = (
                isinstance(func, ast.Name) and func.id == "HTTPException"
            ) or (
                isinstance(func, ast.Attribute) and func.attr == "HTTPException"
            )
            if not is_http_exception:
                continue

            detail_node = node.args[1] if len(node.args) >= 2 else None
            for keyword in node.keywords:
                if keyword.arg == "detail":
                    detail_node = keyword.value
                    break
            if not isinstance(detail_node, ast.Dict):
                continue

            values_by_key: dict[str, ast.expr] = {}
            for key, value in zip(detail_node.keys, detail_node.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    values_by_key[key.value] = value

            code = values_by_key.get("code")
            detail = values_by_key.get("detail")

            def is_string_expression(value: ast.expr | None) -> bool:
                if value is None:
                    return False
                if isinstance(value, ast.Constant):
                    return isinstance(value.value, str) and bool(value.value)
                if isinstance(value, ast.Attribute):
                    return True
                return (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "str"
                )

            if not (is_string_expression(code) and is_string_expression(detail)):
                relative = path.relative_to(api_root.parent.parent)
                violations.append(f"{relative}:{node.lineno}")

    assert violations == []


def test_http_exception_preserves_protocol_headers() -> None:
    response = _error_test_client().get("/header-error")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json() == {
        "code": "HTTP_ERROR",
        "detail": "Thử lại sau.",
    }


def test_application_error_preserves_protocol_headers() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/rate-limited")
    async def rate_limited():
        raise ApplicationError(
            "LOGIN_RATE_LIMITED",
            "Thử đăng nhập quá nhiều lần. Vui lòng thử lại sau.",
            429,
            headers={"Retry-After": "90"},
        )

    response = TestClient(app).get("/rate-limited")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "90"
    assert response.json() == {
        "code": "LOGIN_RATE_LIMITED",
        "detail": "Thử đăng nhập quá nhiều lần. Vui lòng thử lại sau.",
    }
