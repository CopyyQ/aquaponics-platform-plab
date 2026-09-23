from fastapi import APIRouter

from app.api.v1 import (
    aquaponics_systems,
    auth,
    canonical_catalogs,
    canonical_extensions,
    canonical_operations,
    project_scenarios,
    rbac,
    sensor_models,
)
from app.schemas.error import ApiErrorResponse

COMMON_ERROR_RESPONSES = {
    401: {
        "model": ApiErrorResponse,
        "description": "Authentication failed",
    },
    403: {
        "model": ApiErrorResponse,
        "description": "Permission denied",
    },
    422: {
        "model": ApiErrorResponse,
        "description": "Validation failed",
    },
    500: {
        "model": ApiErrorResponse,
        "description": "Internal server error",
    },
}

api_router = APIRouter(responses=COMMON_ERROR_RESPONSES)
api_router.include_router(auth.router)
api_router.include_router(canonical_operations.router)
api_router.include_router(canonical_extensions.router)
api_router.include_router(rbac.router)
api_router.include_router(aquaponics_systems.router)
api_router.include_router(project_scenarios.router)
api_router.include_router(sensor_models.router)
api_router.include_router(canonical_catalogs.router)
