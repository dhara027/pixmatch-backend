"""
Domain-specific exceptions.
Every exception maps to an HTTP status code and a machine-readable error code.
"""
from typing import Optional


class AppError(Exception):
    """Base exception for all application errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, code: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class AuthenticationError(AppError):
    status_code = 401
    code = "AUTHENTICATION_FAILED"


class AuthorizationError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class RateLimitError(AppError):
    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"


class ExternalServiceError(AppError):
    status_code = 502
    code = "EXTERNAL_SERVICE_ERROR"


class FileValidationError(AppError):
    status_code = 400
    code = "INVALID_FILE"


class SSRFAttemptError(AppError):
    status_code = 400
    code = "INVALID_URL"
