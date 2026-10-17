"""JSON logs with the request ID on every line (TRD §16.5). Shipped to Loki."""

from __future__ import annotations

import logging
import sys

import structlog


def configure(service: str, level: str = "INFO") -> None:
    logging.basicConfig(stream=sys.stdout, format="%(message)s", level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)


def bind_request(request_id: str) -> None:
    structlog.contextvars.bind_contextvars(request_id=request_id)


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
