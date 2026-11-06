"""Unhandled errors and ERROR log lines go to Sentry when SENTRY_DSN is set; otherwise nothing."""

import re
from typing import Any

import sentry_sdk
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
from sentry_sdk.types import Event, Hint

from app.core.config import settings
from app.core.logging import _context as _log_fields

# Migration 0018's pattern: every Bot API URL (httpx breadcrumbs, HTTPStatusError messages) has it.
_BOT_TOKEN = re.compile(r"bot[0-9]+:[A-Za-z0-9_-]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def scrub(value: Any) -> Any:
    """Bot tokens and email addresses out of every string of an event or breadcrumb, whichever
    field they ended up in (message, log params, exception value, breadcrumb URL...)."""
    if isinstance(value, str):
        return _EMAIL.sub("<email>", _BOT_TOKEN.sub("bot<token>", value))
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(item) for item in value]
    return value


def _before_send(event: Event, hint: Hint) -> Event:
    scrubbed: Event = scrub(event)
    # Runs synchronously where the error was captured, so a job's log_context is still set here.
    fields = _log_fields.get() or {}
    tags: dict[str, str] = {key: fields[key] for key in ("tenant_id", "report_id") if key in fields}
    scrubbed.setdefault("tags", {}).update(tags)
    return scrubbed


def init_error_tracking(component: str) -> None:
    if not settings.SENTRY_DSN:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.REPORTAI_VERSION,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=0,
        # Locals hold transcripts, extracted report data and decrypted credentials.
        include_local_variables=False,
        # Telegram repeats the webhook secret in this header on every update.
        event_scrubber=EventScrubber(
            denylist=[*DEFAULT_DENYLIST, "x-telegram-bot-api-secret-token"]
        ),
        # With tracing off, sentry-trace/baggage (they carry the DSN's public key) would only reach
        # Telegram, the AI providers and tenant-chosen base URLs, for nothing.
        trace_propagation_targets=[],
        before_send=_before_send,
        before_breadcrumb=lambda crumb, hint: scrub(crumb),
    )
    sentry_sdk.get_global_scope().set_tag("component", component)
