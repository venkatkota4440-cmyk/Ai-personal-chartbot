"""Error categories and handlers.

Clients receive {"error": {"category", "message", "request_id", "fields"?}}.
Stack traces and internal details never leave the server.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class ErrorCategory(StrEnum):
    VALIDATION = "validation_error"
    AUTHENTICATION = "authentication_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    FORBIDDEN = "forbidden"
    CSRF = "csrf_failed"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    INTERNAL = "internal_error"
    UNAVAILABLE = "service_unavailable"
    AI_UNAVAILABLE = "ai_unavailable"
    AI_INVALID_OUTPUT = "ai_invalid_output"
    AI_REFUSED = "ai_refused"


_STATUS_BY_CATEGORY = {
    ErrorCategory.VALIDATION: 422,
    ErrorCategory.AUTHENTICATION: 401,
    ErrorCategory.INVALID_CREDENTIALS: 401,
    ErrorCategory.FORBIDDEN: 403,
    ErrorCategory.CSRF: 403,
    ErrorCategory.NOT_FOUND: 404,
    ErrorCategory.CONFLICT: 409,
    ErrorCategory.RATE_LIMITED: 429,
    ErrorCategory.PAYLOAD_TOO_LARGE: 413,
    ErrorCategory.INTERNAL: 500,
    ErrorCategory.UNAVAILABLE: 503,
    ErrorCategory.AI_UNAVAILABLE: 503,
    # The provider answered, but with output that failed validation; it was discarded, not used.
    ErrorCategory.AI_INVALID_OUTPUT: 502,
    ErrorCategory.AI_REFUSED: 422,
}


class AppError(Exception):
    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        fields: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.headers = headers
        self.fields = fields

    @property
    def status_code(self) -> int:
        return _STATUS_BY_CATEGORY[self.category]


def not_found(resource: str = "Resource") -> AppError:
    # Same response for "missing" and "belongs to someone else" so IDs cannot be probed.
    return AppError(ErrorCategory.NOT_FOUND, f"{resource} not found")


def error_body(category: ErrorCategory, message: str, fields: list[dict[str, str]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"category": category.value, "message": message, "request_id": request_id_var.get()}
    if fields:
        body["fields"] = fields
    return {"error": body}


def _http_category(status: int) -> ErrorCategory:
    for category, code in _STATUS_BY_CATEGORY.items():
        if code == status:
            return category
    return ErrorCategory.INTERNAL if status >= 500 else ErrorCategory.VALIDATION


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            error_body(exc.category, exc.message, exc.fields), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Echo the location and reason only, never the submitted value (it may be a password).
        fields = [
            {"field": ".".join(str(p) for p in err.get("loc", ()) if p != "body"), "message": str(err.get("msg"))}
            for err in exc.errors()
        ]
        return JSONResponse(error_body(ErrorCategory.VALIDATION, "Request validation failed", fields), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        category = _http_category(exc.status_code)
        message = "Not found" if exc.status_code == 404 else "Request could not be processed"
        if exc.status_code == 405:
            message = "Method not allowed"
        return JSONResponse(error_body(category, message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(error_body(ErrorCategory.INTERNAL, "An unexpected error occurred"), status_code=500)
