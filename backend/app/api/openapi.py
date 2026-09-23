from copy import deepcopy

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
MUTATION_METHODS = {"post", "put", "patch", "delete"}


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

                if "_id}" in path:
                    add("404", "Requested resource was not found")
                if method in MUTATION_METHODS:
                    add("409", "Request conflicts with current resource state")
                if path == "/api/v1/auth/change-password":
                    add("400", "Request cannot be applied")
                if (
                    path == "/api/v1/aquaponics-systems"
                    and method == "post"
                ):
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
