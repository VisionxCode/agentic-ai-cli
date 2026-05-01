from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Iterator
from contextlib import contextmanager


_current_job_logger: ContextVar[logging.Logger | None] = ContextVar(
    "current_job_logger", default=None
)


@contextmanager
def job_logging_context(logger: logging.Logger) -> Iterator[None]:
    token = _current_job_logger.set(logger)
    try:
        yield
    finally:
        _current_job_logger.reset(token)


def current_job_logger() -> logging.Logger | None:
    return _current_job_logger.get()


def log_tool_usage(tool_name: str, **fields: object) -> None:
    logger = current_job_logger()
    if logger is None:
        return
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("TOOL %s %s", tool_name, details)
