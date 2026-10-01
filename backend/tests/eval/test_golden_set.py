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
from pathlib import Path

import pytest

from app.core.logging import describe_exception
from app.services import llm
from app.services.agent.nodes.extract import extract_node, validate_node
from app.services.agent.state import AgentState
from tests.eval.golden import Case, Report, build_cases, grade

pytestmark = pytest.mark.eval

MIN_ACCURACY = 0.90
MAX_INVENTED = 0
# Parallel requests: enough to finish in minutes, few enough to stay under provider rate limits.
_CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "4"))


@pytest.fixture(autouse=True)
def _fresh_provider_clients() -> None:
    # pytest-asyncio gives every test its own event loop; a provider client cached by an
    # earlier test would reuse HTTP connections bound to a loop that is already closed.
    llm.clear_client_cache()


async def _extract(case: Case) -> dict[str, object]:
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
    extracted = await extract_node.__wrapped__(state)
    validated = await validate_node.__wrapped__(extracted)
    if validated.last_validation_error:
        raise ValueError(f"invalid extraction: {validated.last_validation_error[:300]}")
    return validated.extracted_fields or {}


async def run_golden_set(cases: list[Case]) -> Report:
    report = Report()
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def run(case: Case) -> None:
        async with gate:
            try:
                actual = await _extract(case)
            except Exception as exc:  # noqa: BLE001 — one broken case is a result, not a crash
                report.errors[case.id] = describe_exception(exc)
                return
        report.outcomes.extend(grade(case, actual))

    await asyncio.gather(*(run(case) for case in cases))
    return report


async def test_extraction_meets_the_fase_2_gate() -> None:
    report = await run_golden_set(build_cases())
    print("\n" + report.render())
    if path := os.environ.get("EVAL_REPORT"):
        Path(path).write_text(
            json.dumps(
                {"accuracy": report.accuracy, "invented": report.count("invented"),
                 "by_field": report.breakdown("field"), "errors": report.errors},
                ensure_ascii=False,
                indent=2,
            )
        )

    assert not report.errors, f"cases that produced no extraction: {report.errors}"
    assert report.count("invented") <= MAX_INVENTED, "fields were filled with values the message never said"
    assert report.accuracy >= MIN_ACCURACY, f"field accuracy {report.accuracy:.1%} is below {MIN_ACCURACY:.0%}"
