from pydantic import BaseModel, ConfigDict


class ApiValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    message: str
    type: str | None = None


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    detail: str
    errors: list[ApiValidationIssue] | None = None
    request_id: str | None = None
