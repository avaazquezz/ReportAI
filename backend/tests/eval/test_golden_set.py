"""Golden-set eval for the extraction node — synthetic cases only, never real client data
(project-wide decision, see PROJECT_ROADMAP.md). Costs real Anthropic API calls; excluded
from `make test`, run explicitly via `make eval`.
"""

import json
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pytest

from app.services.agent.nodes.extract import extract_node
from app.services.agent.state import AgentState

pytestmark = pytest.mark.eval

_GOLDEN_SET_DIR = Path(__file__).parent / "golden_set"
_FUZZY_MATCH_THRESHOLD = 0.85


def _load_cases() -> list[dict[str, Any]]:
    return [json.loads(path.read_text()) for path in sorted(_GOLDEN_SET_DIR.glob("*.json"))]


def _values_match(expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, list):
        return isinstance(actual, list) and set(expected) == set(actual)
    if isinstance(expected, str):
        if not isinstance(actual, str):
            return False
        return SequenceMatcher(None, expected.lower(), actual.lower()).ratio() >= _FUZZY_MATCH_THRESHOLD
    return expected == actual


async def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    state = AgentState(
        thread_id=str(uuid.uuid4()),
        tenant_id=uuid.uuid4(),
        channel_connection_id=uuid.uuid4(),
        channel_type="telegram",
        sender_id="eval",
        report_id=uuid.uuid4(),
        raw_payload={},
        incoming_text=case["input_text"],
        document_type_name=case["document_type_name"],
        field_schema=case["field_schema"],
        prompt_instructions=case.get("prompt_instructions"),
    )
    result_state = await extract_node.__wrapped__(state)

    expected = case["expected_fields"]
    actual = result_state.extracted_fields or {}
    field_results = {
        field: _values_match(expected_value, actual.get(field))
        for field, expected_value in expected.items()
    }
    return {"case": case, "actual": actual, "field_results": field_results}


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["document_type_name"] + ":" + c["input_text"][:20])
async def test_golden_case_extraction_accuracy(case: dict[str, Any]) -> None:
    outcome = await _run_case(case)
    failed_fields = [f for f, ok in outcome["field_results"].items() if not ok]
    assert not failed_fields, (
        f"Extraction mismatch for fields {failed_fields}.\n"
        f"Expected: {outcome['case']['expected_fields']}\nActual:   {outcome['actual']}"
    )


async def test_golden_set_overall_accuracy_report() -> None:
    """Not a pass/fail gate by itself (each case above already asserts) — prints a
    per-field accuracy breakdown so a regression shows *where* extraction got worse,
    not just that it did."""
    cases = _load_cases()
    outcomes = [await _run_case(case) for case in cases]

    total_fields = sum(len(o["field_results"]) for o in outcomes)
    correct_fields = sum(sum(o["field_results"].values()) for o in outcomes)
    accuracy = correct_fields / total_fields if total_fields else 0.0

    print(f"\nGolden-set field accuracy: {correct_fields}/{total_fields} ({accuracy:.1%})")
    for outcome in outcomes:
        wrong = [f for f, ok in outcome["field_results"].items() if not ok]
        if wrong:
            print(f"  {outcome['case']['document_type_name']!r}: wrong fields {wrong}")
