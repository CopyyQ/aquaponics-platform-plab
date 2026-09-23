from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import ApplicationError
from app.schemas.error import ApiErrorResponse, ApiValidationIssue


logger = logging.getLogger(__name__)

DEFAULT_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "AUTHENTICATION_REQUIRED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}

DEFAULT_ERROR_MESSAGES = {
    400: "Yêu cầu không hợp lệ.",
    401: "Chưa đăng nhập hoặc phiên đăng nhập không hợp lệ.",
    403: "Bạn không có quyền thực hiện thao tác này.",
    404: "Không tìm thấy tài nguyên yêu cầu.",
    409: "Thao tác xung đột với trạng thái dữ liệu hiện tại.",
    422: "Dữ liệu gửi lên không hợp lệ.",
    500: "Hệ thống gặp lỗi khi xử lý yêu cầu. Vui lòng thử lại sau.",
    503: "Dịch vụ tạm thời chưa sẵn sàng. Vui lòng thử lại sau.",
}


def _error_response(
    status_code: int,
    code: str,
    detail: str,
    *,
    errors: list[ApiValidationIssue] | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> ORJSONResponse:
    payload = ApiErrorResponse(
        code=code,
        detail=detail,
        errors=errors,
        request_id=request_id,
    ).model_dump(exclude_none=True)
    response_headers = dict(headers or {})
    if status_code == 401:
        response_headers.setdefault("WWW-Authenticate", "Bearer")
    return ORJSONResponse(
        status_code=status_code,
        content=payload,
        headers=response_headers or None,
    )


async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> ORJSONResponse:
    request_id = uuid4().hex if exc.status_code >= 500 else None
    if exc.status_code >= 500:
        logger.error(
            "application_error request_id=%s method=%s path=%s code=%s",
            request_id,
            request.method,
            request.url.path,
            exc.code,
        )
    if not exc.expose_message:
        return _error_response(
            500,
            "INTERNAL_SERVER_ERROR",
            DEFAULT_ERROR_MESSAGES[500],
            request_id=request_id,
        )
    issues = [
        ApiValidationIssue(
            field=item.field,
            message=item.message,
            type=item.type,
        )
        for item in exc.errors
    ] or None
    return _error_response(
        exc.status_code,
        exc.code,
        exc.message,
        errors=issues,
        request_id=request_id,
        headers=exc.headers,
    )


def _normalize_http_detail(
    status_code: int,
    detail: object,
) -> tuple[str, str, list[ApiValidationIssue] | None]:
    code = DEFAULT_ERROR_CODES.get(status_code, "HTTP_ERROR")
    message = DEFAULT_ERROR_MESSAGES.get(
        status_code,
        "Yêu cầu không thể được xử lý.",
    )
    issues = None

    if isinstance(detail, str):
        if status_code == 404 and detail == "Not Found":
            return code, message, None
        return code, detail, None

    if isinstance(detail, dict):
        raw_code = detail.get("code")
        raw_message = detail.get("detail")
        if isinstance(raw_code, str):
            code = raw_code
        if isinstance(raw_message, str):
            message = raw_message
        invalid_fields = detail.get("invalid_fields")
        if isinstance(invalid_fields, list):
            issues = [
                ApiValidationIssue(
                    field=str(field),
                    message="Giá trị không hợp lệ.",
                )
                for field in invalid_fields
            ]
    return code, message, issues


def _validation_issues(
    exc: RequestValidationError,
) -> list[ApiValidationIssue]:
    return [
        ApiValidationIssue(
            field=".".join(str(part) for part in error.get("loc", ())) or None,
            message=str(error.get("msg", "Giá trị không hợp lệ.")),
            type=str(error.get("type")) if error.get("type") else None,
        )
        for error in exc.errors()
    ]


async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> ORJSONResponse:
    del request
    return _error_response(
        422,
        "VALIDATION_ERROR",
        DEFAULT_ERROR_MESSAGES[422],
        errors=_validation_issues(exc),
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> ORJSONResponse:
    del request
    code, message, issues = _normalize_http_detail(
        exc.status_code,
        exc.detail,
    )
    return _error_response(
        exc.status_code,
        code,
        message,
        errors=issues,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> ORJSONResponse:
    request_id = uuid4().hex
    logger.error(
        "unhandled_api_error request_id=%s method=%s path=%s exception_type=%s",
        request_id,
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return _error_response(
        500,
        "INTERNAL_SERVER_ERROR",
        DEFAULT_ERROR_MESSAGES[500],
        request_id=request_id,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        ApplicationError,
        application_error_handler,
    )
    app.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,
    )
    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )
    app.add_exception_handler(
        Exception,
        unhandled_exception_handler,
    )
