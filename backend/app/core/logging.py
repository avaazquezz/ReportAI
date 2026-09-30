import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

_context: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar("log_context", default=None)


@contextmanager
def log_context(**fields: object) -> Iterator[None]:
    """Attach fields (report_id, tenant_id...) to every log line emitted inside the block."""
    token = _context.set({**(_context.get() or {}), **{k: str(v) for k, v in fields.items()}})
    try:
        yield
    finally:
        _context.reset(token)


def describe_exception(exc: BaseException) -> str:
    """str(exc) alone is empty for some exceptions (asyncio.TimeoutError()), which turned
    failed reports into blank error details."""
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **(_context.get() or {}),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """One JSON object per line on stdout (plain text in development), for app and uvicorn
    alike — `docker logs` output that can be grepped by tenant_id / report_id."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        if settings.is_development
        else JsonFormatter()
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
