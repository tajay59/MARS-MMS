"""Errors and their RFC 9457 problem-details bodies (TRD §14).

An out-of-scope resource raises `NotFound`, never `Forbidden` (ADR-16, CLAUDE.md rule 4).
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status = 500
    code = "internal_error"
    title = "Internal error"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extra = extra

    def problem(self, request_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": f"https://errors.aws-mms/{self.code}",
            "title": self.title,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
        }
        if request_id:
            body["request_id"] = request_id
        body.update(self.extra)
        return body


class ValidationFailed(AppError):
    status, code, title = 422, "validation_failed", "Validation failed"


class Unauthenticated(AppError):
    status, code, title = 401, "unauthenticated", "Sign in required"


class Forbidden(AppError):
    """The user is in scope but their role may not do this. Out of scope is `NotFound`."""

    status, code, title = 403, "forbidden", "Not allowed"


class NotFound(AppError):
    status, code, title = 404, "not_found", "Not found"


class Conflict(AppError):
    status, code, title = 409, "conflict", "Conflict"


class VersionConflict(Conflict):
    """Optimistic concurrency: the `version` the caller sent is stale."""

    code, title = "version_conflict", "The record changed. Reload and try again"


class RateLimited(AppError):
    status, code, title = 429, "rate_limited", "Too many requests"
