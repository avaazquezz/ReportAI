"""Golden-set eval of the extraction step against the configured model. Costs real API calls;
excluded from `make test`, run explicitly with `make eval` (add -s to see the report).

The set (tests/eval/golden.py) is generated with known ground truth. The gate is the one Fase 2
promised: high field accuracy, and no field invented — a value for something the message never
said is the failure a formal document cannot afford.
"""

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.logging import describe_exception
from app.services import company_ai, instance_settings, llm
from app.services.agent.nodes.extract import extract_node, validate_node
from app.services.agent.state import AgentState, ToolUsage
from tests.eval.golden import Case, Report, build_cases, current_commit, grade

pytestmark = pytest.mark.eval

MIN_ACCURACY = 0.90
MAX_INVENTED = 0
# Parallel requests: enough to finish in minutes, few enough to stay under provider rate limits.
_CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "4"))
# Shorter than the job queue's 30/120/300 s, same idea: a transient provider error isn't a miss.
_PROVIDER_RETRY_DELAYS = (5, 20)


@pytest.fixture(autouse=True)
def _installation_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    # The eval grades the model this checkout is configured with (EXTRACTION_* or the panel's
    # settings), not a company's own: no company stands behind these made-up reports.
    async def installation(_tenant_id: uuid.UUID) -> instance_settings.AIConfig:
        # EVAL_COMPANY_PROVIDER=openai (with EVAL_COMPANY_API_KEY, optional EVAL_COMPANY_MODEL) grades
        # a provider of the hosted service's list, called exactly as a company's own key would be:
        # how a provider earns `validated` in services/ai_providers.py.
        if provider := os.environ.get("EVAL_COMPANY_PROVIDER"):
            return company_ai.extraction_from({
                "extraction_provider": provider,
                "extraction_model": os.environ.get("EVAL_COMPANY_MODEL", ""),
                "extraction_api_key": os.environ["EVAL_COMPANY_API_KEY"],
            })
        return await instance_settings.ai_config()

    monkeypatch.setattr(company_ai, "extraction_for", installation)


@pytest.fixture(autouse=True)
def _fresh_provider_clients() -> None:
    # pytest-asyncio gives every test its own event loop; a provider client cached by an
    # earlier test would reuse HTTP connections bound to a loop that is already closed.
    llm.clear_client_cache()


@dataclass
class Spend:
    """What the run cost, read off the same usage records production logs per call."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    models: set[str] = field(default_factory=set)

    def add(self, usage: ToolUsage | None) -> None:
        if usage is None:
            return
        self.calls += 1
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.cost_usd += usage.cost_usd or 0.0
        if usage.model_used:
            self.models.add(usage.model_used)


async def _extract(case: Case, spend: Spend) -> dict[str, object]:
    state = AgentState(
        thread_id=str(uuid.uuid4()),
        tenant_id=uuid.uuid4(),
        channel_connection_id=uuid.uuid4(),
        channel_type="telegram",
        sender_id="eval",
        report_id=uuid.uuid4(),
        raw_payload={},
        incoming_text=case.text,
        language=case.language,
        timezone="Europe/Madrid",
        received_at=case.received_at,
        document_type_name=case.document_type_name,
        field_schema=case.field_schema,
        prompt_instructions=case.prompt_instructions,
    )
    # The graph's own loop (graph._route_after_validate): an extraction that fails validation goes
    # back to the model with the error, up to the same limit as in production.
    while True:
        state = await extract_node.__wrapped__(state)
        spend.add(state.last_tool_usage)
        state = await validate_node.__wrapped__(state)
        if state.last_validation_error is None:
            return state.extracted_fields or {}
        if state.validation_retries >= settings.MAX_VALIDATION_RETRIES:
            raise InvalidExtraction(state.last_validation_error[:300])


class InvalidExtraction(Exception):
    """The model's answer stayed invalid after every retry: a real failure, never retried."""


async def run_golden_set(cases: list[Case], spend: Spend) -> Report:
    report = Report()
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def run(case: Case) -> None:
        async with gate:
            for delay in (*_PROVIDER_RETRY_DELAYS, None):
                try:
                    actual = await _extract(case, spend)
                    break
                except InvalidExtraction as exc:
                    report.errors[case.id] = f"invalid extraction: {exc}"
                    return
                except Exception as exc:  # noqa: BLE001 — one broken case is a result, not a crash
                    if delay is None:
                        report.errors[case.id] = describe_exception(exc)
                        return
                    # A provider hiccup (overloaded, timeout): production's job queue retries it too.
                    report.retried.setdefault(case.id, []).append(describe_exception(exc))
                    await asyncio.sleep(delay)
        report.outcomes.extend(grade(case, actual))

    await asyncio.gather(*(run(case) for case in cases))
    return report


async def test_extraction_meets_the_fase_2_gate() -> None:
    spend = Spend()
    report = await run_golden_set(build_cases(), spend)
    print("\n" + report.render())
    print(f"\nSpend: {spend.calls} model calls, {spend.input_tokens} in / {spend.output_tokens} out tokens, ${spend.cost_usd:.4f}")
    if path := os.environ.get("EVAL_REPORT"):
        Path(path).write_text(json.dumps(_published(report, spend), ensure_ascii=False, indent=2) + "\n")

    assert not report.errors, f"cases that produced no extraction: {report.errors}"
    assert report.count("invented") <= MAX_INVENTED, "fields were filled with values the message never said"
    assert report.accuracy >= MIN_ACCURACY, f"field accuracy {report.accuracy:.1%} is below {MIN_ACCURACY:.0%}"


def _published(report: Report, spend: Spend) -> dict[str, object]:
    """The run as docs/evals/ publishes it: enough to tell what was graded, with what, and how."""
    return {
        "eval": "golden_set",
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": current_commit(),
        "provider": os.environ.get("EVAL_COMPANY_PROVIDER") or "installation",
        "models": sorted(spend.models),
        "gate": {"min_accuracy": MIN_ACCURACY, "max_invented": MAX_INVENTED},
        "cases": len({o.case_id for o in report.outcomes} | set(report.errors)),
        "fields": len(report.outcomes),
        "accuracy": round(report.accuracy, 4),
        "verdicts": {v: report.count(v) for v in ("correct", "wrong", "missed", "invented")},
        "failed_cases": report.errors,
        "retried_cases": len(report.retried),
        "spend": {"model_calls": spend.calls, "input_tokens": spend.input_tokens,
                  "output_tokens": spend.output_tokens, "cost_usd": round(spend.cost_usd, 4)},
        "by_type": report.breakdown("type"),
        "by_field": report.breakdown("field"),
    }
