from typing import Any

import pytest
import sentry_sdk

from app.core.config import settings
from app.core.error_tracking import _before_send, init_error_tracking, scrub
from app.core.logging import log_context

_BOT_URL = "https://api.telegram.org/bot123456:AAH-x_9zQ/sendMessage"


def test_scrub_removes_bot_tokens_and_emails_and_keeps_the_rest() -> None:
    event = {
        "level": "error",
        "logentry": {
            "message": "Failed to send password reset email to %s",
            "params": ("ana.lopez+obra@example.co.uk",),
            "formatted": "Failed to send password reset email to ana.lopez+obra@example.co.uk",
        },
        "exception": {
            "values": [{"type": "HTTPStatusError", "value": f"Client error '404 Not Found' for url '{_BOT_URL}'"}]
        },
        "breadcrumbs": {
            "values": [
                {"message": "Report sent to ana@example.com", "data": {"url": _BOT_URL, "status_code": 404}}
            ]
        },
    }

    assert scrub(event) == {
        "level": "error",
        "logentry": {
            "message": "Failed to send password reset email to %s",
            "params": ["<email>"],
            "formatted": "Failed to send password reset email to <email>",
        },
        "exception": {
            "values": [
                {
                    "type": "HTTPStatusError",
                    "value": "Client error '404 Not Found' for url 'https://api.telegram.org/bot<token>/sendMessage'",
                }
            ]
        },
        "breadcrumbs": {
            "values": [
                {
                    "message": "Report sent to <email>",
                    "data": {"url": "https://api.telegram.org/bot<token>/sendMessage", "status_code": 404},
                }
            ]
        },
    }


def test_events_raised_inside_a_job_carry_its_tenant_and_report() -> None:
    with log_context(report_id="r-1", tenant_id="t-1", job="process_message"):
        inside = _before_send({"message": "boom", "tags": {"component": "worker"}}, {})
    outside = _before_send({"message": "boom"}, {})

    assert inside["tags"] == {"component": "worker", "report_id": "r-1", "tenant_id": "t-1"}
    assert "tenant_id" not in outside.get("tags", {})


def _capture_init(monkeypatch: pytest.MonkeyPatch, dsn: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    calls: list[dict[str, Any]] = []
    tags: dict[str, str] = {}

    class _Scope:
        def set_tag(self, key: str, value: str) -> None:
            tags[key] = value

    monkeypatch.setattr(settings, "SENTRY_DSN", dsn)
    monkeypatch.setattr(sentry_sdk, "init", lambda **options: calls.append(options))
    monkeypatch.setattr(sentry_sdk, "get_global_scope", _Scope)
    return calls, tags


def test_without_a_dsn_nothing_is_initialised(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, tags = _capture_init(monkeypatch, "")

    init_error_tracking("api")

    assert calls == [] and tags == {}


def test_with_a_dsn_it_sends_no_pii_no_traces_and_scrubs_breadcrumbs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls, tags = _capture_init(monkeypatch, "https://public@o1.ingest.de.sentry.io/1")

    init_error_tracking("worker")

    [options] = calls
    assert options["send_default_pii"] is False and options["traces_sample_rate"] == 0
    assert options["max_request_body_size"] == "never" and options["include_local_variables"] is False
    assert options["release"] == settings.REPORTAI_VERSION and options["environment"] == settings.ENVIRONMENT
    assert "x-telegram-bot-api-secret-token" in options["event_scrubber"].denylist
    assert options["trace_propagation_targets"] == []
    assert options["before_breadcrumb"]({"data": {"url": _BOT_URL}}, {}) == {
        "data": {"url": "https://api.telegram.org/bot<token>/sendMessage"}
    }
    assert tags == {"component": "worker"}
