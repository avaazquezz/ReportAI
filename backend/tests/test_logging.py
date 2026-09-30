import json
import logging

from app.core.logging import JsonFormatter, describe_exception, log_context


def _format(message: str) -> dict[str, str]:
    record = logging.LogRecord("app.test", logging.WARNING, __file__, 1, message, None, None)
    return json.loads(JsonFormatter().format(record))


def test_json_lines_carry_the_report_and_tenant_ids_only_inside_the_context() -> None:
    with log_context(report_id="r-1", tenant_id="t-1"):
        inside = _format("pipeline failed")
    outside = _format("later line")

    assert inside["message"] == "pipeline failed" and inside["level"] == "WARNING"
    assert inside["report_id"] == "r-1" and inside["tenant_id"] == "t-1"
    assert "report_id" not in outside


def test_describe_exception_is_never_blank() -> None:
    assert describe_exception(TimeoutError()) == "TimeoutError"  # str(TimeoutError()) == ""
    assert describe_exception(ValueError("bad input")) == "ValueError: bad input"
