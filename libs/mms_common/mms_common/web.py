"""FastAPI plumbing every service shares: request IDs, problem-details errors, and the
`/health`, `/ready` and `/metrics` endpoints (TRD §3.0)."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

from mms_common.errors import AppError
from mms_common.ids import new_id
from mms_common.logging import bind_request

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ReadyCheck = Callable[[], Awaitable[bool]]
PROBLEM = "application/problem+json"


def install(app: FastAPI, ready_checks: dict[str, ReadyCheck] | None = None) -> None:
    """Add the request-ID middleware, error handlers and the health routes.

    `ready_checks` maps a dependency name ("mongo", "redis", "kafka") to a coroutine
    that returns True when it is reachable.
    """
    checks = ready_checks if ready_checks is not None else {}
    app.state.ready_checks = checks

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        rid = incoming if _SAFE_ID.match(incoming) else new_id()
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        bind_request(rid)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            exc.problem(getattr(request.state, "request_id", None)),
            status_code=exc.status,
            media_type=PROBLEM,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Framework errors (unknown path, wrong method) as problem details too."""
        codes = {404: "not_found", 405: "method_not_allowed"}
        code = codes.get(exc.status_code, "http_error")
        body = {
            "type": f"https://errors.aws-mms/{code}",
            "title": str(exc.detail),
            "status": exc.status_code,
            "code": code,
            "request_id": getattr(request.state, "request_id", None),
        }
        return JSONResponse(
            body, status_code=exc.status_code, media_type=PROBLEM, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the submitted values back: they may hold passwords or operators.
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        body = {
            "type": "https://errors.aws-mms/validation_failed",
            "title": "Validation failed",
            "status": 422,
            "code": "validation_failed",
            "errors": errors,
            "request_id": getattr(request.state, "request_id", None),
        }
        return JSONResponse(body, status_code=422, media_type=PROBLEM)

    router = APIRouter(include_in_schema=False)

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    async def ready() -> JSONResponse:
        results: dict[str, bool] = {}
        for name, check in checks.items():
            try:
                results[name] = bool(await check())
            except Exception:  # noqa: BLE001 - an unreachable dependency means not ready
                results[name] = False
        ok = all(results.values())
        return JSONResponse(
            {"status": "ready" if ok else "not_ready", "checks": results},
            status_code=200 if ok else 503,
        )

    @router.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(router)
