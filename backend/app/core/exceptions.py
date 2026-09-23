from dataclasses import dataclass


class DomainError(Exception):
    """Base error for expected business-rule failures."""


class ResourceNotFoundError(DomainError):
    pass


class ProjectAccessDeniedError(DomainError):
    pass


class ResourceDisabledError(DomainError):
    pass


class InvalidLifecycleTransitionError(DomainError):
    pass


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    field: str | None
    message: str
    type: str | None = None


class ApplicationError(DomainError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        errors: tuple[ErrorDetail, ...] = (),
        expose_message: bool = True,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.errors = errors
        self.expose_message = expose_message
        self.headers = dict(headers or {})


class InternalInvariantError(ApplicationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 500, expose_message=False)
